from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.llm import build_system_prompt, chat_with_tools
from app.llm_claude import get_claude_llm
from app.memory.store import get_memory_store
from app.rate_limit import limiter
from app.skills.base import get_ollama_tools, get_server_tools, get_skill, serialize_tool_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Response models ────────────────────────────────────────


class TextChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    tts: bool = False
    # Set to true when the calling client can execute client_executed tools
    # (i.e. it will send TOOL_RESULT_CLIENT-equivalent responses).  Defaults
    # to false so calendar/device tools are excluded from HTTP chat.
    client_tools: bool = False


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


def _summarize_tool_results(tool_results: list[dict]) -> str:
    """Build a minimal user-facing confirmation from raw tool results.

    Used only when the LLM returns empty content after the tool loop and a
    follow-up call also yields nothing — the last-resort fallback.
    """
    parts: list[str] = []
    for tr in tool_results:
        tool_name = tr.get("tool", "")
        result = tr.get("result", {})
        if not isinstance(result, dict):
            continue
        if result.get("success"):
            if tool_name == "set_reminder":
                remind_at = result.get("remind_at", "")
                if remind_at:
                    try:
                        dt = datetime.fromisoformat(remind_at)
                        parts.append(
                            f"Reminder set for {dt.strftime('%a')} {dt.day} {dt.strftime('%b, %H:%M')}."
                        )
                    except ValueError:
                        parts.append("Reminder set.")
                else:
                    parts.append("Reminder set.")
            elif tool_name == "save_note":
                parts.append("Note saved.")
            elif tool_name == "create_calendar_event":
                parts.append("Calendar event created.")
            else:
                parts.append("Done.")
        elif "error" in result:
            parts.append(f"Error: {result['error']}")
    return " ".join(parts) if parts else "Done."


async def _run_chat_pipeline(
    user_text: str,
    history: list[dict],
    client_tools: bool = False,
) -> tuple[str, list[dict], list[dict], str | None]:
    """Run the LLM + tool-dispatch pipeline. Returns (reply, tool_calls, tool_results, error).

    client_tools=True includes client_executed skills in the tool list (the
    caller is responsible for handling any tool results they send back).
    client_tools=False (default) uses only server-side tools so the LLM never
    calls calendar/device skills that the server cannot execute.
    """

    memory_store = get_memory_store()
    memory_context = None
    if memory_store:
        results = await memory_store.search(user_text, top_k=5)
        if results:
            memory_context = results

    tools = get_ollama_tools() if client_tools else get_server_tools()

    system_prompt = build_system_prompt(
        memory_context,
        available_tools=tools,
        memory_available=memory_store is not None and memory_store.available,
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-20:])
    messages.append({"role": "user", "content": user_text})

    claude = get_claude_llm()
    response = await claude.chat(messages, tools if tools else None)

    if "error" in response and response["error"]:
        return response["message"]["content"], [], [], response["error"]

    assistant_message = response.get("message", {})
    all_tool_calls: list[dict] = []
    all_tool_results: list[dict] = []

    tool_calls = assistant_message.get("tool_calls")
    if tool_calls:
        # OpenAI-compatible providers (Groq, NVIDIA) require the assistant message with
        # tool_calls to appear in history before the tool result messages.
        openai_tcs = []
        for tc in tool_calls:
            func = tc.get("function", {})
            args = func.get("arguments", {})
            entry: dict = {
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "arguments": json.dumps(args) if isinstance(args, dict) else (args or "{}"),
                },
            }
            if tc.get("id"):
                entry["id"] = tc["id"]
            openai_tcs.append(entry)
        messages.append({
            "role": "assistant",
            "content": assistant_message.get("content") or "",
            "tool_calls": openai_tcs,
        })

        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            tool_args = func.get("arguments", {})
            tc_id = tc.get("id")
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
            tool_result_msg: dict = {
                "role": "tool",
                "content": serialize_tool_result(skill, tool_name, result),
            }
            if tc_id:
                tool_result_msg["tool_call_id"] = tc_id
            messages.append(tool_result_msg)

        response = await claude.chat(messages, tools if tools else None)
        assistant_message = response.get("message", {})

    reply = assistant_message.get("content", "")

    # When tool calls were made and the post-tool response has empty content,
    # make one more call (no tools — forces a text reply) to get a user-facing
    # confirmation.  If that is also empty, build a summary from tool results.
    if not reply and all_tool_calls:
        followup = await claude.chat(messages, None)
        reply = followup.get("message", {}).get("content", "") or ""
        if not reply:
            reply = _summarize_tool_results(all_tool_results)

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
@limiter.limit(get_settings().rate_limit_llm)
async def text_chat(request: Request, body: TextChatRequest):
    """Text chat with Athena. Set tts=true to also get the reply as audio."""
    if not get_settings().any_llm_configured:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_llm_available",
                "message": (
                    "No LLM provider is configured. "
                    "Set at least one of: ANTHROPIC_API_KEY, GROQ_API_KEY, "
                    "NVIDIA_API_KEY, or OLLAMA_BASE_URL."
                ),
            },
        )

    reply, tool_calls, tool_results, error = await _run_chat_pipeline(
        body.message, body.history, body.client_tools
    )

    if error == "llm_providers_failed":
        raise HTTPException(
            status_code=502,
            detail={
                "error": "llm_providers_failed",
                "message": reply,
            },
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
@limiter.limit(get_settings().rate_limit_llm)
async def audio_chat(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (WAV or raw PCM, 16kHz 16-bit mono)"),
    history: str = Form(default="[]", description="JSON array of past messages"),
    tts: bool = Form(default=True, description="Return reply as audio"),
    client_tools: bool = Form(default=False, description="Include client-executed tools"),
):
    """Send audio, get a transcription + LLM reply (optionally with TTS audio back)."""
    if not get_settings().any_llm_configured:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_llm_available",
                "message": (
                    "No LLM provider is configured. "
                    "Set at least one of: ANTHROPIC_API_KEY, GROQ_API_KEY, "
                    "NVIDIA_API_KEY, or OLLAMA_BASE_URL."
                ),
            },
        )

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
        transcript, parsed_history, client_tools
    )

    if error == "llm_providers_failed":
        raise HTTPException(
            status_code=502,
            detail={
                "error": "llm_providers_failed",
                "message": reply,
            },
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
