from __future__ import annotations

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.chat.pipeline import run_chat_turn
from app.config import get_settings
from app.db import User
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Response models ─────────────────────────────────────────────────────────


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


# ── Shared helpers ──────────────────────────────────────────────────────────


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
        raw_audio = await asyncio.wait_for(
            asyncio.to_thread(_synthesize_speech, text),
            timeout=get_settings().tts_timeout,
        )
        if not raw_audio:
            return None
        return base64.b64encode(raw_audio).decode("ascii")
    except asyncio.TimeoutError:
        logger.warning("TTS synthesis timed out after %ds", get_settings().tts_timeout)
        return None
    except Exception:
        logger.exception("TTS synthesis failed")
        return None


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/text", response_model=TextChatResponse)
@limiter.limit(get_settings().rate_limit_llm)
async def text_chat(
    request: Request,
    body: TextChatRequest,
    current_user: User = Depends(get_current_user),
):
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

    result = await run_chat_turn(
        body.message, body.history,
        client_capabilities=body.client_tools,
        user_id=current_user.id,
    )

    if result.error == "llm_providers_failed":
        raise HTTPException(
            status_code=502,
            detail={
                "error": "llm_providers_failed",
                "message": result.reply,
            },
        )

    audio_b64 = None
    if body.tts and not result.error:
        audio_b64 = await _get_tts_audio(result.reply)

    return TextChatResponse(
        reply=result.reply,
        audio_base64=audio_b64,
        tool_calls=result.tool_calls,
        tool_results=result.tool_results,
        error=result.error,
    )


@router.post("/audio", response_model=AudioChatResponse)
@limiter.limit(get_settings().rate_limit_llm)
async def audio_chat(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (WAV or raw PCM, 16kHz 16-bit mono)"),
    history: str = Form(default="[]", description="JSON array of past messages"),
    tts: bool = Form(default=True, description="Return reply as audio"),
    client_tools: bool = Form(default=False, description="Include client-executed tools"),
    current_user: User = Depends(get_current_user),
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

    try:
        transcript = await asyncio.wait_for(
            asyncio.to_thread(transcribe_audio, audio_bytes),
            timeout=get_settings().stt_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("STT timed out after %ds", get_settings().stt_timeout)
        return AudioChatResponse(
            transcript="",
            reply="",
            error="Transcription timed out",
        )

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

    result = await run_chat_turn(
        transcript, parsed_history,
        client_capabilities=client_tools,
        user_id=current_user.id,
    )

    if result.error == "llm_providers_failed":
        raise HTTPException(
            status_code=502,
            detail={
                "error": "llm_providers_failed",
                "message": result.reply,
            },
        )

    audio_b64 = None
    if tts and not result.error:
        audio_b64 = await _get_tts_audio(result.reply)

    return AudioChatResponse(
        transcript=transcript,
        reply=result.reply,
        audio_base64=audio_b64,
        tool_calls=result.tool_calls,
        tool_results=result.tool_results,
        error=result.error,
    )
