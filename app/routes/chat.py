from __future__ import annotations

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from app.llm import build_system_prompt, chat_with_tools
from app.llm_claude import get_claude_llm
from app.memory.store import get_memory_store
from app.skills.base import get_ollama_tools, get_skill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Response models ────────────────────────────────────────


class TextChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    tts: bool = False


class TextChatResponse(BaseModel):
    reply: str
    audio_base64: str | None = None
    tool_calls: list[dict] = []
    tool_results: list[dict] = []
    error: str | None = None


class AudioChatResponse(BaseModel):
    transcript: str
    reply: str
    audio_base64: str | None = None
    tool_calls: list[dict] = []
    tool_results: list[dict] = []
    error: str | None = None


# ── Shared helpers ─────────────────────────────────────────


async def _run_chat_pipeline(
    user_text: str,
    history: list[dict],
) -> tuple[str, list[dict], list[dict], str | None]:
    """Run the LLM + tool-dispatch pipeline. Returns (reply, tool_calls, tool_results, error)."""

    memory_store = get_memory_store()
    memory_context = None
    if memory_store:
        results = await memory_store.search(user_text, top_k=5)
        if results:
            memory_context = results

    system_prompt = build_system_prompt(memory_context)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-20:])
    messages.append({"role": "user", "content": user_text})

    tools = get_ollama_tools()

    # Use Claude as primary, Ollama as fallback
    claude = get_claude_llm()
    response = await claude.chat(messages, tools if tools else None)

    if "error" in response and response["error"]:
        return response["message"]["content"], [], [], response["error"]

    assistant_message = response.get("message", {})
    all_tool_calls: list[dict] = []
    all_tool_results: list[dict] = []

    tool_calls = assistant_message.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            tool_args = func.get("arguments", {})
            all_tool_calls.append({"tool": tool_name, "args": tool_args})

            skill = get_skill(tool_name)
            if skill is None:
                result = {"error": f"Unknown skill: {tool_name}"}
            elif skill.client_executed:
                result = {"error": f"Skill '{tool_name}' must be executed on the client device"}
            elif skill.handler:
                try:
                    handler_result = skill.handler(**tool_args)
                    if asyncio.iscoroutine(handler_result):
                        result = await asyncio.wait_for(handler_result, timeout=skill.timeout)
                    else:
                        result = handler_result
                except asyncio.TimeoutError:
                    result = {"error": f"Skill '{tool_name}' timed out"}
                except Exception as e:
                    logger.exception("Skill %s failed", tool_name)
                    result = {"error": str(e)}
            else:
                result = {"error": f"Skill '{tool_name}' has no handler"}

            all_tool_results.append({"tool": tool_name, "result": result})
            messages.append({"role": "tool", "content": json.dumps(result)})

        response = await claude.chat(messages, tools if tools else None)
        assistant_message = response.get("message", {})

    reply = assistant_message.get("content", "")

    if memory_store:
        await memory_store.add_memory(user_text, {"role": "user", "type": "chat"})
        await memory_store.add_memory(reply, {"role": "assistant", "type": "chat"})

    return reply, all_tool_calls, all_tool_results, None


async def _get_tts_audio(text: str) -> str | None:
    """Synthesize text to speech and return base64-encoded PCM audio, or None."""
    if not text:
        return None

    try:
        from app.websocket.voice import PIPER_AVAILABLE, _synthesize_speech
    except ImportError:
        return None

    if not PIPER_AVAILABLE:
        return None

    try:
        raw_audio = await asyncio.to_thread(_synthesize_speech, text)
        if not raw_audio:
            return None
        return base64.b64encode(raw_audio).decode("ascii")
    except Exception:
        logger.exception("TTS synthesis failed")
        return None


# ── Endpoints ──────────────────────────────────────────────


@router.post("/text", response_model=TextChatResponse)
async def text_chat(body: TextChatRequest):
    """Text chat with Athena. Set tts=true to also get the reply as audio."""

    reply, tool_calls, tool_results, error = await _run_chat_pipeline(
        body.message, body.history
    )

    audio_b64 = None
    if body.tts and not error:
        audio_b64 = await _get_tts_audio(reply)

    return TextChatResponse(
        reply=reply,
        audio_base64=audio_b64,
        tool_calls=tool_calls,
        tool_results=tool_results,
        error=error,
    )


@router.post("/audio", response_model=AudioChatResponse)
async def audio_chat(
    audio: UploadFile = File(..., description="Audio file (WAV or raw PCM, 16kHz 16-bit mono)"),
    history: str = Form(default="[]", description="JSON array of past messages"),
    tts: bool = Form(default=True, description="Return reply as audio"),
):
    """Send audio, get a transcription + LLM reply (optionally with TTS audio back)."""

    try:
        from app.websocket.voice import WHISPER_AVAILABLE, transcribe_audio
    except ImportError:
        return AudioChatResponse(
            transcript="",
            reply="",
            error="Voice modules not available",
        )

    if not WHISPER_AVAILABLE:
        return AudioChatResponse(
            transcript="",
            reply="",
            error="Whisper STT not installed — cannot transcribe audio",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        return AudioChatResponse(
            transcript="",
            reply="",
            error="Empty audio file",
        )

    transcript = await asyncio.to_thread(transcribe_audio, audio_bytes)
    if not transcript or transcript == "[STT unavailable]":
        return AudioChatResponse(
            transcript=transcript or "",
            reply="",
            error="Could not transcribe audio",
        )

    try:
        parsed_history = json.loads(history)
    except json.JSONDecodeError:
        parsed_history = []

    reply, tool_calls, tool_results, error = await _run_chat_pipeline(
        transcript, parsed_history
    )

    audio_b64 = None
    if tts and not error:
        audio_b64 = await _get_tts_audio(reply)

    return AudioChatResponse(
        transcript=transcript,
        reply=reply,
        audio_base64=audio_b64,
        tool_calls=tool_calls,
        tool_results=tool_results,
        error=error,
    )
