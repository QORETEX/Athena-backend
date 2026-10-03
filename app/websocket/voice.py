from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from limits import parse as parse_rate_limit

from app.config import get_settings
from app.rate_limit import limiter
from app.schemas import AssistantState, MessageType

logger = logging.getLogger(__name__)

# ── Graceful degradation flags ──────────────────────────────────────────────

WHISPER_AVAILABLE = False
PIPER_AVAILABLE = False
VAD_AVAILABLE = False

try:
    from faster_whisper import WhisperModel

    WHISPER_AVAILABLE = True
    logger.info("faster-whisper available")
except ImportError:
    logger.info("faster-whisper not installed — STT disabled")

try:
    from piper import PiperVoice

    PIPER_AVAILABLE = True
    logger.info("piper-tts available")
except ImportError:
    logger.info("piper-tts not installed — TTS disabled")

try:
    import torch

    VAD_AVAILABLE = True
    logger.info("torch available — VAD enabled")
except ImportError:
    logger.info("torch not installed — VAD disabled, relying on client audio_end")

from app.audio.denoise import denoise_audio  # noqa: E402 — must follow optional imports above

# ── Lazy model singletons ───────────────────────────────────────────────────

_whisper_model = None
_piper_voice = None
_vad_model = None
_vad_utils = None


def get_whisper():
    global _whisper_model
    if _whisper_model is None and WHISPER_AVAILABLE:
        settings = get_settings()
        logger.info("Loading Whisper model: %s", settings.whisper_model_size)
        _whisper_model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        logger.info("Whisper model loaded")
    return _whisper_model


def get_piper():
    global _piper_voice
    if _piper_voice is None and PIPER_AVAILABLE:
        settings = get_settings()
        logger.info("Loading Piper voice: %s", settings.piper_model_path)
        _piper_voice = PiperVoice.load(settings.piper_model_path)
        logger.info("Piper voice loaded")
    return _piper_voice


def get_vad():
    global _vad_model, _vad_utils
    if _vad_model is None and VAD_AVAILABLE:
        logger.info("Loading Silero VAD")
        _vad_model, _vad_utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        logger.info("Silero VAD loaded")
    return _vad_model, _vad_utils


# ── Helpers ──────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # 16-bit PCM


async def send_msg(ws: WebSocket, msg_type: MessageType, payload: dict):
    await ws.send_json({"type": msg_type.value, "payload": payload})


async def set_state(ws: WebSocket, state: AssistantState):
    await send_msg(ws, MessageType.STATUS, {"state": state.value})


# ── VAD ──────────────────────────────────────────────────────────────────────


def check_vad(audio_buffer: bytes | bytearray) -> bool:
    if not VAD_AVAILABLE:
        return False

    settings = get_settings()
    model, _ = get_vad()
    if model is None:
        return False

    min_samples = int(SAMPLE_RATE * settings.vad_min_silence_ms / 1000)
    check_window = int(SAMPLE_RATE * 1.5)  # look at the last 1.5s

    buf_samples = len(audio_buffer) // BYTES_PER_SAMPLE
    if buf_samples < min_samples:
        return False

    start = max(0, buf_samples - check_window)
    chunk = audio_buffer[start * BYTES_PER_SAMPLE :]
    audio_np = (
        np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
    )
    audio_tensor = torch.from_numpy(audio_np)

    window_size = 512
    tail_samples = int(SAMPLE_RATE * settings.vad_min_silence_ms / 1000)
    tail_start = max(0, len(audio_tensor) - tail_samples)
    tail = audio_tensor[tail_start:]

    all_silent = True
    for i in range(0, len(tail) - window_size, window_size):
        frame = tail[i : i + window_size]
        if len(frame) < window_size:
            break
        confidence = model(frame, SAMPLE_RATE).item()
        if confidence > settings.vad_threshold:
            all_silent = False
            break

    return all_silent


# ── STT ──────────────────────────────────────────────────────────────────────


def transcribe_audio(audio_bytes: bytes) -> str:
    model = get_whisper()
    if model is None:
        return "[STT unavailable]"

    cleaned = denoise_audio(audio_bytes)

    audio_np = np.frombuffer(cleaned, dtype=np.int16).astype(np.float32) / 32768.0

    if len(audio_np) == 0:
        return ""

    segments, _ = model.transcribe(audio_np, beam_size=5)
    text = " ".join(seg.text for seg in segments).strip()
    return text


# ── TTS ──────────────────────────────────────────────────────────────────────


def _synthesize_speech(text: str) -> bytes:
    voice = get_piper()
    if voice is None:
        return b""

    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize(text, wf)

    buf.seek(0)
    with wave.open(buf, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    return raw


async def stream_tts(text: str, ws: WebSocket):
    if not PIPER_AVAILABLE or not text:
        await send_msg(ws, MessageType.TTS_END, {})
        return

    try:
        raw_audio = await asyncio.wait_for(
            asyncio.to_thread(_synthesize_speech, text),
            timeout=get_settings().tts_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("TTS synthesis timed out after %ds", get_settings().tts_timeout)
        await send_msg(ws, MessageType.TTS_END, {})
        return
    except Exception:
        logger.exception("TTS synthesis failed")
        await send_msg(ws, MessageType.TTS_END, {})
        return

    if not raw_audio:
        await send_msg(ws, MessageType.TTS_END, {})
        return

    chunk_size = 4096
    seq = 0
    for i in range(0, len(raw_audio), chunk_size):
        if asyncio.current_task().cancelled():
            return
        chunk = raw_audio[i : i + chunk_size]
        b64 = base64.b64encode(chunk).decode("ascii")
        await send_msg(ws, MessageType.TTS_CHUNK, {"audio_base64": b64, "seq": seq})
        seq += 1

    await send_msg(ws, MessageType.TTS_END, {})


# ── Core pipeline ────────────────────────────────────────────────────────────


async def process_utterance(
    audio_data: bytes,
    ws: WebSocket,
    session_history: list[dict],
    client_tool_futures: dict[str, asyncio.Future],
    user_id: int | None = None,
):
    try:
        # 1. Transcribe
        await set_state(ws, AssistantState.TRANSCRIBING)
        try:
            transcript = await asyncio.wait_for(
                asyncio.to_thread(transcribe_audio, audio_data),
                timeout=get_settings().stt_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("STT timed out after %ds", get_settings().stt_timeout)
            await send_msg(ws, MessageType.ERROR, {"message": "Transcription timed out"})
            await set_state(ws, AssistantState.IDLE)
            return

        if not transcript or transcript == "[STT unavailable]":
            await send_msg(
                ws,
                MessageType.FINAL_TRANSCRIPT,
                {"text": transcript or ""},
            )
            if not transcript:
                await set_state(ws, AssistantState.IDLE)
                return

        await send_msg(ws, MessageType.FINAL_TRANSCRIPT, {"text": transcript})

        # 2. Think
        await set_state(ws, AssistantState.THINKING)

        # Enforce the same per-IP LLM rate limit as HTTP routes
        _rate_item = parse_rate_limit(get_settings().rate_limit_llm)
        _client_ip = _get_ws_client_ip(ws)
        if not limiter.limiter.hit(_rate_item, _client_ip):
            await send_msg(ws, MessageType.ERROR, {
                "message": "Rate limit exceeded. Please wait before sending another message."
            })
            await set_state(ws, AssistantState.IDLE)
            return

        # Guard: no provider configured
        if not get_settings().any_llm_configured:
            await send_msg(ws, MessageType.ERROR, {
                "code": "no_llm_available",
                "message": "No LLM provider is configured.",
            })
            await set_state(ws, AssistantState.IDLE)
            return

        # 3. Run shared pipeline with WS-specific callbacks
        from app.chat.pipeline import run_chat_turn
        from app.memory.store import get_memory_store

        async def _on_tool_call(tool_name: str, args: dict) -> None:
            await send_msg(ws, MessageType.TOOL_CALL, {"tool": tool_name, "args": args})

        async def _on_tool_result(tool_name: str, result: dict) -> None:
            await send_msg(ws, MessageType.TOOL_RESULT, {"tool": tool_name, "result": result})

        result = await run_chat_turn(
            transcript,
            list(session_history),
            client_capabilities=True,
            user_id=user_id,
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
            client_tool_futures=client_tool_futures,
        )

        if result.error == "llm_providers_failed":
            await send_msg(ws, MessageType.ERROR, {
                "code": "llm_providers_failed",
                "message": result.reply,
            })
            await set_state(ws, AssistantState.IDLE)
            return

        # 4. Send reply text
        await send_msg(ws, MessageType.ASSISTANT_TEXT, {"text": result.reply})

        # 5. TTS
        await set_state(ws, AssistantState.SPEAKING)
        await stream_tts(result.reply, ws)

        # 6. Done
        await set_state(ws, AssistantState.IDLE)

        # 7. Update session history (caller's list, not the copy we passed in)
        session_history.append({"role": "user", "content": transcript})
        session_history.append({"role": "assistant", "content": result.reply})
        if len(session_history) > 40:
            session_history[:] = session_history[-40:]

        # 8. Persist to memory & conversation log
        memory_store = get_memory_store()
        if memory_store:
            await memory_store.add_memory(
                transcript, {"role": "user", "type": "conversation"}
            )
            await memory_store.add_memory(
                result.reply, {"role": "assistant", "type": "conversation"}
            )

        await _log_conversation(transcript, result.reply, result.tool_calls or None, user_id=user_id)

    except asyncio.CancelledError:
        logger.info("Pipeline cancelled (barge-in)")
        raise
    except Exception:
        logger.exception("Pipeline error")
        try:
            await send_msg(ws, MessageType.ERROR, {"message": "Internal error"})
            await set_state(ws, AssistantState.IDLE)
        except Exception:
            pass


async def _log_conversation(
    transcript: str,
    assistant_text: str,
    tool_calls: list | None,
    user_id: int | None = None,
):
    if user_id is None:
        return
    try:
        from app.db import ConversationLog, async_session

        if async_session is None:
            return

        async with async_session() as session:
            now = datetime.now(timezone.utc)
            session.add(
                ConversationLog(
                    user_id=user_id,
                    timestamp=now,
                    role="user",
                    content=transcript,
                )
            )
            session.add(
                ConversationLog(
                    user_id=user_id,
                    timestamp=now,
                    role="assistant",
                    content=assistant_text,
                    tool_calls=json.dumps(tool_calls) if tool_calls else None,
                )
            )
            await session.commit()
    except Exception:
        logger.exception("Failed to log conversation")


# ── WebSocket endpoint ───────────────────────────────────────────────────────

router = APIRouter()

_WS_MAX_TEXT_BYTES = 64 * 1024  # 64 KB cap on individual text control messages

# Per-IP concurrent connection tracking (asyncio is single-threaded; no lock needed)
_ws_connections_per_ip: dict[str, int] = {}


def _get_ws_client_ip(ws: WebSocket) -> str:
    """Mirror of rate_limit.get_client_ip, adapted for WebSocket objects."""
    settings = get_settings()
    if settings.trust_proxy:
        xff = ws.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip()
    return (ws.client.host if ws.client else None) or "127.0.0.1"


@router.websocket("/ws/voice")
async def voice_endpoint(ws: WebSocket):
    client_ip = _get_ws_client_ip(ws)
    settings = get_settings()
    current_conns = _ws_connections_per_ip.get(client_ip, 0)
    if current_conns >= settings.ws_max_conn_per_ip:
        # Must accept before closing per the WebSocket protocol
        await ws.accept()
        await ws.close(code=1008)  # 1008 = Policy Violation
        return
    _ws_connections_per_ip[client_ip] = current_conns + 1

    # Initialize before try so finally can always reference them
    current_task: asyncio.Task | None = None
    client_tool_futures: dict[str, asyncio.Future] = {}

    try:
        await ws.accept()

        # Auth: first message must be {"type":"auth","token":"<access_token>"} within 5 s.
        try:
            _raw_auth = await asyncio.wait_for(ws.receive(), timeout=5.0)
        except asyncio.TimeoutError:
            await ws.close(code=1008)
            return

        _auth_text = _raw_auth.get("text", "")
        if not _auth_text:
            await ws.close(code=1008)
            return

        try:
            _auth_msg = json.loads(_auth_text)
        except json.JSONDecodeError:
            await ws.close(code=1008)
            return

        if _auth_msg.get("type") != "auth" or not _auth_msg.get("token"):
            await ws.close(code=1008)
            return

        try:
            from app.auth.tokens import decode_access_token
            from app.db import User as _User, async_session as _async_session
            _payload = decode_access_token(_auth_msg["token"])
            _user_id = int(_payload["sub"])
            async with _async_session() as _session:
                _user = await _session.get(_User, _user_id)
                if _user is None or not _user.is_active:
                    await ws.close(code=1008)
                    return
        except Exception:
            await ws.close(code=1008)
            return

        ws.state.user_id = _user_id
        logger.info("Voice WebSocket connected")

        audio_buffer = bytearray()
        session_history: list[dict] = []

        while True:
            raw = await ws.receive()

            # Binary frames = audio data
            if raw.get("type") == "websocket.receive" and "bytes" in raw and raw["bytes"]:
                incoming = raw["bytes"]
                if len(audio_buffer) + len(incoming) > settings.ws_max_audio_bytes:
                    await send_msg(ws, MessageType.ERROR, {
                        "message": "Audio buffer limit exceeded (max 10 MB). Recording stopped."
                    })
                    await ws.close(code=1009)
                    return
                audio_buffer.extend(incoming)
                if await asyncio.to_thread(check_vad, bytes(audio_buffer)):
                    data_copy = bytes(audio_buffer)
                    audio_buffer.clear()
                    current_task = asyncio.create_task(
                        process_utterance(
                            data_copy,
                            ws,
                            session_history,
                            client_tool_futures,
                            user_id=_user_id,
                        )
                    )
                continue

            # Text frames = JSON control messages
            text = raw.get("text")
            if not text:
                continue

            if len(text.encode()) > _WS_MAX_TEXT_BYTES:
                await send_msg(ws, MessageType.ERROR, {"message": "Text message too large"})
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            if msg_type == MessageType.WAKE_DETECTED.value:
                audio_buffer.clear()
                if current_task and not current_task.done():
                    current_task.cancel()
                    current_task = None
                await set_state(ws, AssistantState.LISTENING)

            elif msg_type == MessageType.AUDIO_START.value:
                audio_buffer.clear()

            elif msg_type == MessageType.AUDIO_END.value:
                if audio_buffer:
                    data_copy = bytes(audio_buffer)
                    audio_buffer.clear()
                    current_task = asyncio.create_task(
                        process_utterance(
                            data_copy,
                            ws,
                            session_history,
                            client_tool_futures,
                            user_id=_user_id,
                        )
                    )

            elif msg_type == MessageType.INTERRUPT.value:
                if current_task and not current_task.done():
                    current_task.cancel()
                    current_task = None
                await set_state(ws, AssistantState.LISTENING)

            elif msg_type == MessageType.TOOL_RESULT_CLIENT.value:
                tool_name = payload.get("tool", "")
                result = payload.get("result", {})
                future = client_tool_futures.get(tool_name)
                if future and not future.done():
                    future.set_result(result)

            elif msg_type == MessageType.PING.value:
                await send_msg(ws, MessageType.PONG, {})

    except WebSocketDisconnect:
        logger.info("Voice WebSocket disconnected")
    except Exception:
        logger.exception("Voice WebSocket error")
    finally:
        count = _ws_connections_per_ip.get(client_ip, 1)
        if count <= 1:
            _ws_connections_per_ip.pop(client_ip, None)
        else:
            _ws_connections_per_ip[client_ip] = count - 1
        if current_task and not current_task.done():
            current_task.cancel()
        for future in client_tool_futures.values():
            if not future.done():
                future.cancel()
