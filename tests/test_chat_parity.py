"""Parity tests: all three entry points share one pipeline.

Each test is parametrized over ["text", "audio", "ws"] and patches
app.chat.pipeline.* so the assertions apply identically to every entry point.
"""
from __future__ import annotations

import io
import json
import wave
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.schemas import MessageType
from main import app


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def test_client(override_get_db):
    return TestClient(app)


@pytest.fixture
def auth_token(override_get_db):
    tc = TestClient(app)
    resp = tc.post("/api/auth/register", json={
        "email": "parity@test.com",
        "password": "testpass123",
        "name": "Parity User",
    })
    assert resp.status_code == 200, f"Register failed: {resp.json()}"
    return resp.json()["access_token"]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _silent_wav() -> bytes:
    """16kHz mono 16-bit WAV with 0.5 s of silence."""
    samples = b"\x00" * (16000 * 2 // 2)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(samples)
    buf.seek(0)
    return buf.read()


def _make_mock_llm(reply: str = "Acknowledged.", capture: dict | None = None):
    """Mock LLM that records messages and tools passed to it on each call."""
    async def chat(messages, tools=None):
        if capture is not None:
            capture.setdefault("messages", []).append(list(messages))
            capture.setdefault("tools_per_call", []).append(list(tools or []))
        return {"message": {"role": "assistant", "content": reply}}

    mock_llm = MagicMock()
    mock_llm.chat = chat
    return mock_llm


def _collect_ws_messages(ws, max_count: int = 40) -> list[dict]:
    """Collect WS messages until STATUS idle or ERROR or max_count reached."""
    collected: list[dict] = []
    for _ in range(max_count):
        try:
            msg = ws.receive_json()
            collected.append(msg)
            if msg.get("type") == MessageType.STATUS and msg.get("payload", {}).get("state") == "idle":
                break
            if msg.get("type") == MessageType.ERROR:
                break
        except Exception:
            break
    return collected


def _base_patches(mock_llm, extra: dict | None = None):
    """Common patches applied to every invocation."""
    patches = {
        "app.chat.pipeline.get_memory_store": MagicMock(return_value=None),
        "app.chat.pipeline.get_claude_llm": MagicMock(return_value=mock_llm),
    }
    if extra:
        patches.update(extra)
    return patches


def _fake_settings():
    """Settings stub that passes the 503 guard without a real LLM key."""
    from app.config import get_settings as _real
    s = MagicMock(wraps=_real())
    s.any_llm_configured = True
    s.rate_limit_llm = "10000/minute"
    s.max_tool_rounds = 4
    s.stt_timeout = 30
    s.tts_timeout = 30
    return s


def _apply_patches(stack: ExitStack, mock_llm, extra_patches: dict | None = None):
    """Enter base patches + any extra patches into the given ExitStack."""
    fake_s = _fake_settings()
    stack.enter_context(patch("app.routes.chat.get_settings", return_value=fake_s))
    stack.enter_context(patch("app.chat.pipeline.get_memory_store", return_value=None))
    stack.enter_context(patch("app.chat.pipeline.get_claude_llm", return_value=mock_llm))
    for target, replacement in (extra_patches or {}).items():
        stack.enter_context(patch(target, new=replacement))


def invoke_text(client, token, message, mock_llm, extra_patches=None):
    with ExitStack() as stack:
        _apply_patches(stack, mock_llm, extra_patches)
        return client.post(
            "/api/chat/text",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": message, "history": [], "tts": False},
        )


def invoke_audio(client, token, message, mock_llm, extra_patches=None):
    wav_data = _silent_wav()
    with ExitStack() as stack:
        _apply_patches(stack, mock_llm, extra_patches)
        stack.enter_context(patch("app.websocket.voice.transcribe_audio", return_value=message))
        return client.post(
            "/api/chat/audio",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", wav_data, "audio/wav")},
            data={"tts": "false"},
        )


def _ws_session_patch(token: str):
    """Patch app.db.async_session so the WS auth finds a mock active user.

    The WS endpoint uses async_session directly (not get_db), so the test DB
    created by override_get_db is invisible to it.  We need a separate shim.
    """
    from app.auth.tokens import decode_access_token
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception:
        user_id = 1

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, pk):
            mock_user = MagicMock()
            mock_user.is_active = True
            return mock_user

        def add(self, *args):
            pass

        async def commit(self):
            pass

    return patch("app.db.async_session", new=lambda: _FakeSession())


def _ws_settings_patch():
    """Patch get_settings in voice.py so the LLM guard passes in tests."""
    from app.config import get_settings as real_get_settings
    fake_s = MagicMock(wraps=real_get_settings())
    fake_s.any_llm_configured = True
    fake_s.rate_limit_llm = "10000/minute"
    fake_s.max_tool_rounds = 4
    fake_s.vad_threshold = 0.5
    fake_s.vad_min_silence_ms = 700
    fake_s.ws_max_audio_bytes = 10 * 1024 * 1024
    fake_s.ws_max_conn_per_ip = 3
    fake_s.trust_proxy = False
    fake_s.stt_timeout = 30
    fake_s.tts_timeout = 30
    return patch("app.websocket.voice.get_settings", return_value=fake_s)


def invoke_ws(client, token, message, mock_llm, extra_patches=None):
    ws_messages: list[dict] = []
    with ExitStack() as stack:
        _apply_patches(stack, mock_llm, extra_patches)
        stack.enter_context(patch("app.websocket.voice.transcribe_audio", return_value=message))
        stack.enter_context(patch("app.websocket.voice.stream_tts", new=AsyncMock()))
        stack.enter_context(_ws_session_patch(token))
        stack.enter_context(_ws_settings_patch())
        with client.websocket_connect("/ws/voice") as ws:
            ws.send_json({"type": "auth", "token": token})
            ws.send_bytes(b"\x00" * 200)  # fill buffer so AUDIO_END has data
            ws.send_json({"type": "audio_end", "payload": {}})
            ws_messages = _collect_ws_messages(ws)
    return ws_messages


def do_invoke(mode, client, token, message, mock_llm, extra_patches=None):
    if mode == "text":
        return invoke_text(client, token, message, mock_llm, extra_patches)
    elif mode == "audio":
        return invoke_audio(client, token, message, mock_llm, extra_patches)
    else:
        return invoke_ws(client, token, message, mock_llm, extra_patches)


def get_reply_and_error(mode, response):
    """Extract (reply: str, error: str | None) from the endpoint response."""
    if mode == "text":
        d = response.json()
        return d.get("reply", ""), d.get("error")
    elif mode == "audio":
        d = response.json()
        return d.get("reply", ""), d.get("error")
    else:
        for msg in response:
            if msg.get("type") == MessageType.ASSISTANT_TEXT:
                return msg["payload"]["text"], None
            if msg.get("type") == MessageType.ERROR:
                return "", msg["payload"].get("code", "error")
        return "", "no_reply"


def get_http_error_code(mode, response):
    """Return the HTTP status code (text/audio) or WS ERROR code."""
    if mode in ("text", "audio"):
        return response.status_code
    else:
        for msg in response:
            if msg.get("type") == MessageType.ERROR:
                return msg["payload"].get("code")
        return None


# ── Test 1: system prompt has today's date and 14-day calendar ───────────────


@pytest.mark.parametrize("mode", ["text", "audio", "ws"])
def test_system_prompt_has_date_and_calendar(mode, test_client, auth_token):
    """System prompt passed to LLM must include the current date and 14-day calendar."""
    capture: dict = {}
    mock_llm = _make_mock_llm(capture=capture)

    do_invoke(mode, test_client, auth_token, "Hello.", mock_llm)

    messages_list = capture.get("messages", [])
    assert messages_list, f"LLM was never called on {mode!r} path"
    system_prompt = messages_list[0][0]["content"]

    now = datetime.now(timezone.utc)
    assert str(now.year) in system_prompt, f"Year {now.year} not in system prompt ({mode})"

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert any(w in system_prompt for w in weekdays), (
        f"No weekday name found in system prompt ({mode})"
    )

    assert "Next 14 days:" in system_prompt, f"14-day calendar missing from system prompt ({mode})"


# ── Test 2: skills filter — client_executed only on ws ───────────────────────


@pytest.mark.parametrize("mode", ["text", "audio", "ws"])
def test_client_executed_tools_only_on_ws(mode, test_client, auth_token):
    """HTTP paths must exclude client_executed skills; WS path must include them."""
    capture: dict = {}
    mock_llm = _make_mock_llm(capture=capture)

    do_invoke(mode, test_client, auth_token, "Hi.", mock_llm)

    tools_offered = capture.get("tools_per_call", [[]])[0]
    tool_names = {t.get("function", {}).get("name") for t in tools_offered}

    if mode in ("text", "audio"):
        assert "device_control" not in tool_names, (
            f"device_control (client_executed) offered on {mode!r} path"
        )
        assert "create_calendar_event" not in tool_names, (
            f"create_calendar_event (client_executed) offered on {mode!r} path"
        )
    else:
        # WS path must expose client_executed tools for the device to handle
        assert "device_control" in tool_names, "device_control missing on ws path"
        assert "create_calendar_event" in tool_names, "create_calendar_event missing on ws path"


# ── Test 3: empty-key argument doesn't crash ─────────────────────────────────


@pytest.mark.parametrize("mode", ["text", "audio", "ws"])
def test_empty_key_arg_does_not_crash(mode, test_client, auth_token):
    """A tool call with an empty-key argument must not crash the pipeline."""
    call_count = 0

    async def chat_with_empty_key(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": "tc1",
                "function": {"name": "list_reminders", "arguments": {"": "bad"}},
            }]}}
        return {"message": {"role": "assistant", "content": "No reminders."}}

    mock_llm = MagicMock()
    mock_llm.chat = chat_with_empty_key

    mock_skill = MagicMock()
    mock_skill.client_executed = False
    mock_skill.returns_external_content = False
    mock_skill.name = "list_reminders"
    mock_skill.enabled_check = None
    mock_skill.return_value = mock_skill  # get_skill(...) returns the skill itself

    extra = {
        "app.chat.pipeline.get_skill": mock_skill,
        "app.chat.pipeline.call_skill_handler": AsyncMock(return_value={"reminders": []}),
    }

    result = do_invoke(mode, test_client, auth_token, "What reminders?", mock_llm, extra)
    reply, error = get_reply_and_error(mode, result)

    assert not error, f"Unexpected error on {mode!r} with empty-key arg: {error!r}"
    assert "No reminders." in reply, f"Expected 'No reminders.' in reply ({mode}), got: {reply!r}"


# ── Test 4: reasoning-only response never appears in reply ───────────────────


@pytest.mark.parametrize("mode", ["text", "audio", "ws"])
def test_reasoning_field_never_in_reply(mode, test_client, auth_token):
    """If the pipeline receives a response with only a 'reasoning' field, it must not leak."""
    reasoning_text = "INTERNAL_CHAIN_OF_THOUGHT"

    async def reasoning_only_chat(messages, tools=None):
        return {"message": {
            "role": "assistant",
            "content": "",
            "reasoning": reasoning_text,
        }}

    mock_llm = MagicMock()
    mock_llm.chat = reasoning_only_chat

    result = do_invoke(mode, test_client, auth_token, "Hi.", mock_llm)
    reply, _ = get_reply_and_error(mode, result)

    assert reasoning_text not in reply, (
        f"Reasoning text leaked into reply on {mode!r} path: {reply!r}"
    )


# ── Test 5: tool error + corrected call → normal reply ───────────────────────


@pytest.mark.parametrize("mode", ["text", "audio", "ws"])
def test_tool_error_then_correct_gives_reply(mode, test_client, auth_token):
    """Round 1 tool fails, round 2 succeeds → pipeline returns the LLM's final reply."""
    call_count = 0

    async def two_round_chat(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": "tc1",
                "function": {"name": "set_reminder", "arguments": {
                    "text": "test", "time": "bad-format",
                }},
            }]}}
        elif call_count == 2:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": "tc2",
                "function": {"name": "set_reminder", "arguments": {
                    "text": "test", "time": "2026-10-01T08:00:00+00:00",
                }},
            }]}}
        return {"message": {"role": "assistant", "content": "Reminder set successfully."}}

    mock_llm = MagicMock()
    mock_llm.chat = two_round_chat

    mock_skill = MagicMock()
    mock_skill.client_executed = False
    mock_skill.returns_external_content = False
    mock_skill.name = "set_reminder"
    mock_skill.enabled_check = None
    mock_skill.return_value = mock_skill  # get_skill(...) returns the skill itself

    extra = {
        "app.chat.pipeline.get_skill": mock_skill,
        "app.chat.pipeline.call_skill_handler": AsyncMock(side_effect=[
            {"error": "Invalid time format"},
            {"success": True, "remind_at": "2026-10-01T08:00:00+00:00"},
        ]),
    }

    result = do_invoke(mode, test_client, auth_token, "Remind me to test.", mock_llm, extra)
    reply, error = get_reply_and_error(mode, result)

    assert not error, f"Unexpected error on {mode!r}: {error!r}"
    assert "Reminder set successfully." in reply, (
        f"Expected final reply on {mode!r}, got: {reply!r}"
    )


# ── Test 6: device_control (client_executed) works on ws ─────────────────────


def test_device_control_dispatched_on_ws(test_client, auth_token):
    """On ws path, device_control is dispatched to the client via future mechanism."""
    call_count = 0

    async def chat_calling_device_control(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": "tc_dc",
                "function": {"name": "device_control", "arguments": {"action": "get_battery"}},
            }]}}
        return {"message": {"role": "assistant", "content": "Your battery is at 85%."}}

    mock_llm = MagicMock()
    mock_llm.chat = chat_calling_device_control

    tool_call_msgs: list[dict] = []
    tool_result_msgs: list[dict] = []

    with (
        patch("app.chat.pipeline.get_memory_store", return_value=None),
        patch("app.chat.pipeline.get_claude_llm", return_value=mock_llm),
        patch("app.websocket.voice.transcribe_audio", return_value="What is my battery?"),
        patch("app.websocket.voice.stream_tts", new=AsyncMock()),
        _ws_session_patch(auth_token),
        _ws_settings_patch(),
    ):
        with test_client.websocket_connect("/ws/voice") as ws:
            ws.send_json({"type": "auth", "token": auth_token})
            ws.send_bytes(b"\x00" * 200)
            ws.send_json({"type": "audio_end", "payload": {}})

            # Collect messages; when TOOL_CALL arrives for device_control,
            # respond immediately as the client would.
            received: list[dict] = []
            for _ in range(50):
                try:
                    msg = ws.receive_json()
                    received.append(msg)
                    if msg.get("type") == MessageType.TOOL_CALL:
                        tool_call_msgs.append(msg)
                        ws.send_json({
                            "type": "tool_result_client",
                            "payload": {
                                "tool": msg["payload"]["tool"],
                                "result": {"battery_level": 85},
                            },
                        })
                    elif msg.get("type") == MessageType.TOOL_RESULT:
                        tool_result_msgs.append(msg)
                    elif msg.get("type") == MessageType.STATUS and msg.get("payload", {}).get("state") == "idle":
                        break
                    elif msg.get("type") == MessageType.ERROR:
                        break
                except Exception:
                    break

    # Verify the TOOL_CALL was sent
    assert tool_call_msgs, "No TOOL_CALL message sent for device_control on ws path"
    assert tool_call_msgs[0]["payload"]["tool"] == "device_control"

    # Verify TOOL_RESULT was sent back to client
    assert tool_result_msgs, "No TOOL_RESULT message sent after device_control"

    # Verify we got the final reply
    assistant_texts = [m for m in received if m.get("type") == MessageType.ASSISTANT_TEXT]
    assert assistant_texts, "No ASSISTANT_TEXT received after device_control dispatch"
    assert "85" in assistant_texts[0]["payload"]["text"]


# ── Test 6b: build_tools parity — all HTTP entry points produce identical tool lists ──


def test_tool_list_identical_across_http_entry_points(test_client, auth_token):
    """For client_capabilities=False, text and audio must pass the same tool list to the LLM."""
    capture_text: dict = {}
    capture_audio: dict = {}

    mock_text = _make_mock_llm(capture=capture_text)
    mock_audio = _make_mock_llm(capture=capture_audio)

    invoke_text(test_client, auth_token, "Hi.", mock_text)
    invoke_audio(test_client, auth_token, "Hi.", mock_audio)

    tools_text = capture_text.get("tools_per_call", [[]])[0]
    tools_audio = capture_audio.get("tools_per_call", [[]])[0]

    def _names(tools: list) -> list[str]:
        return sorted(t.get("function", {}).get("name", "") for t in tools)

    assert _names(tools_text) == _names(tools_audio), (
        "text and audio entry points produced different tool lists:\n"
        f"  text:  {_names(tools_text)}\n"
        f"  audio: {_names(tools_audio)}"
    )


# ── Test 7: all providers failing gives the same error on all entry points ────


@pytest.mark.parametrize("mode", ["text", "audio", "ws"])
def test_all_providers_failing_gives_same_error(mode, test_client, auth_token):
    """When all LLM providers fail, each entry point must report an LLM failure."""
    async def always_fails(messages, tools=None):
        return {
            "message": {"role": "assistant", "content": "groq: rate limited (429)"},
            "error": "llm_providers_failed",
        }

    mock_llm = MagicMock()
    mock_llm.chat = always_fails

    result = do_invoke(mode, test_client, auth_token, "Hello.", mock_llm)

    if mode in ("text", "audio"):
        assert result.status_code == 502, (
            f"Expected 502 on {mode!r} when all providers fail, got {result.status_code}"
        )
        detail = result.json().get("detail", {})
        assert detail.get("error") == "llm_providers_failed"
    else:
        # WS: should receive an ERROR message with code llm_providers_failed
        error_msgs = [m for m in result if m.get("type") == MessageType.ERROR]
        assert error_msgs, f"No ERROR message received on ws path when providers fail"
        assert error_msgs[0]["payload"].get("code") == "llm_providers_failed"
