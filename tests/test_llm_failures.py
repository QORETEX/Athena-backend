"""Tests for LLM failure reporting — no real network calls."""
from __future__ import annotations

import asyncio
import time

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a real HTTPStatusError with the given status code."""
    req = httpx.Request("POST", "https://example.com")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError("", request=req, response=resp)


def _mock_settings(**overrides) -> MagicMock:
    """Return a mock settings object with safe defaults for the new timeout fields."""
    s = MagicMock()
    s.ollama_enabled = False
    s.llm_connect_timeout = 5
    s.llm_read_timeout = 25
    s.llm_chain_deadline = 40
    s.claude_model = "claude-3-haiku"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ── Error classification ──────────────────────────────────────────────────────


def test_classify_401():
    from app.llm_claude import _classify_error
    result = _classify_error(_http_error(401))
    assert "invalid or unauthorized key" in result
    assert "401" in result


def test_classify_403():
    from app.llm_claude import _classify_error
    result = _classify_error(_http_error(403))
    assert "invalid or unauthorized key" in result
    assert "403" in result


def test_classify_404():
    from app.llm_claude import _classify_error
    result = _classify_error(_http_error(404))
    assert "model not found" in result
    assert "404" in result


def test_classify_429():
    from app.llm_claude import _classify_error
    result = _classify_error(_http_error(429))
    assert "rate limited" in result


def test_classify_timeout():
    from app.llm_claude import _classify_error
    # Without elapsed, falls back to plain "timed out"
    assert _classify_error(httpx.TimeoutException("timed out")) == "timed out"


def test_classify_timeout_with_elapsed():
    from app.llm_claude import _classify_error
    result = _classify_error(httpx.TimeoutException("timed out"), elapsed=28.5)
    assert "timed out" in result
    assert "28" in result  # elapsed seconds included


def test_classify_other_status():
    from app.llm_claude import _classify_error
    result = _classify_error(_http_error(500))
    assert "500" in result
    assert "invalid" not in result
    assert "model" not in result


# ── ClaudeLLM orchestration ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_providers_fail_returns_llm_providers_failed():
    """All configured providers raise → error=llm_providers_failed with safe reasons."""
    from app.llm_claude import ClaudeLLM

    llm = object.__new__(ClaudeLLM)
    llm.available = False
    llm.client = None
    llm.settings = MagicMock(claude_model="claude-3-haiku")

    mock_groq = MagicMock()
    mock_groq.available = True
    mock_groq.model = "gpt-oss-20b"
    mock_groq.chat = AsyncMock(side_effect=_http_error(401))

    mock_nvidia = MagicMock()
    mock_nvidia.available = True
    mock_nvidia.model = "llama-70b"
    mock_nvidia.chat = AsyncMock(side_effect=_http_error(404))

    mock_settings = _mock_settings()

    with (
        patch("app.llm_claude.get_groq_llm", return_value=mock_groq),
        patch("app.llm_claude.get_nvidia_llm", return_value=mock_nvidia),
        patch("app.llm_claude.get_settings", return_value=mock_settings),
    ):
        result = await llm.chat([{"role": "user", "content": "hello"}])

    assert result["error"] == "llm_providers_failed"
    content = result["message"]["content"]
    assert "groq" in content
    assert "nvidia" in content
    assert "401" in content
    assert "404" in content


@pytest.mark.asyncio
async def test_skipped_providers_not_in_failure_message():
    """Providers with no key are marked 'skipped' and excluded from the failure reasons."""
    from app.llm_claude import ClaudeLLM

    llm = object.__new__(ClaudeLLM)
    llm.available = False
    llm.client = None
    llm.settings = MagicMock(claude_model="claude-3-haiku")

    mock_groq = MagicMock()
    mock_groq.available = True
    mock_groq.model = "gpt-oss-20b"
    mock_groq.chat = AsyncMock(side_effect=_http_error(429))

    # NVIDIA has no key → will be skipped
    mock_nvidia = MagicMock()
    mock_nvidia.available = False

    mock_settings = _mock_settings()

    with (
        patch("app.llm_claude.get_groq_llm", return_value=mock_groq),
        patch("app.llm_claude.get_nvidia_llm", return_value=mock_nvidia),
        patch("app.llm_claude.get_settings", return_value=mock_settings),
    ):
        result = await llm.chat([{"role": "user", "content": "hello"}])

    assert result["error"] == "llm_providers_failed"
    content = result["message"]["content"]
    assert "groq" in content
    assert "rate limited" in content
    # nvidia was skipped, not failed — should not appear in the reasons
    assert "nvidia" not in content


# ── New tests: chain deadline, retry, error labelling ────────────────────────


@pytest.mark.asyncio
async def test_chain_deadline_stops_chain():
    """Chain deadline expiring after Groq causes NVIDIA to be skipped."""
    from app.llm_claude import ClaudeLLM

    llm = object.__new__(ClaudeLLM)
    llm.available = False
    llm.client = None
    llm.settings = MagicMock(claude_model="claude-3-haiku")

    # Groq sleeps longer than the chain deadline then raises
    async def slow_groq(*args, **kwargs):
        await asyncio.sleep(0.2)
        raise httpx.ReadTimeout("read timeout")

    mock_groq = MagicMock()
    mock_groq.available = True
    mock_groq.model = "gpt-oss-20b"
    mock_groq.chat = slow_groq

    mock_nvidia = MagicMock()
    mock_nvidia.available = True
    mock_nvidia.model = "llama-70b"
    # nvidia.chat would succeed, but the chain deadline expires before we get here
    mock_nvidia.chat = AsyncMock(return_value={"message": {"role": "assistant", "content": "nvidia ok"}})

    # Chain deadline shorter than Groq's sleep — budget is spent when NVIDIA is checked
    mock_settings = _mock_settings(llm_chain_deadline=0.1)

    with (
        patch("app.llm_claude.get_groq_llm", return_value=mock_groq),
        patch("app.llm_claude.get_nvidia_llm", return_value=mock_nvidia),
        patch("app.llm_claude.get_settings", return_value=mock_settings),
    ):
        result = await llm.chat([{"role": "user", "content": "hello"}])

    # Overall request failed because nvidia was never tried
    assert result["error"] == "llm_providers_failed"
    # nvidia.chat must not have been called
    mock_nvidia.chat.assert_not_called()
    # The failure content names nvidia as a skipped-due-to-budget provider
    content = result["message"]["content"]
    assert "nvidia" in content
    assert "exhausted" in content or "skipped" in content


@pytest.mark.asyncio
async def test_no_retry_after_read_timeout():
    """A Groq ReadTimeout propagates to the chain immediately — no retry sleep delay."""
    from app.llm_claude import ClaudeLLM

    llm = object.__new__(ClaudeLLM)
    llm.available = False
    llm.client = None
    llm.settings = MagicMock(claude_model="claude-3-haiku")

    mock_groq = MagicMock()
    mock_groq.available = True
    mock_groq.model = "gpt-oss-20b"
    # ReadTimeout raised immediately (no sleep inside the mock)
    mock_groq.chat = AsyncMock(side_effect=httpx.ReadTimeout("read timeout"))

    mock_nvidia = MagicMock()
    mock_nvidia.available = True
    mock_nvidia.model = "llama-70b"
    mock_nvidia.chat = AsyncMock(return_value={"message": {"role": "assistant", "content": "nvidia ok"}})

    mock_settings = _mock_settings()

    with (
        patch("app.llm_claude.get_groq_llm", return_value=mock_groq),
        patch("app.llm_claude.get_nvidia_llm", return_value=mock_nvidia),
        patch("app.llm_claude.get_settings", return_value=mock_settings),
    ):
        t0 = time.monotonic()
        result = await llm.chat([{"role": "user", "content": "hello"}])
        elapsed = time.monotonic() - t0

    # NVIDIA succeeded after Groq timed out
    assert result.get("error") is None
    assert "nvidia ok" in result["message"]["content"]
    # If Groq had retried, there would be at least a 1-second asyncio.sleep.
    # The whole chain should complete in well under 1 second.
    assert elapsed < 1.0, f"Chain took {elapsed:.2f}s — suggests a retry sleep occurred"


# ── Groq 4xx error handling ───────────────────────────────────────────────────


import json as _json


def _groq_response(status: int, body: dict | None = None) -> httpx.Response:
    """Build a real httpx.Response simulating a Groq API reply."""
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    text = _json.dumps(body) if body else ""
    return httpx.Response(status, text=text, request=req)


def _groq_mock_client(*responses: httpx.Response) -> MagicMock:
    """AsyncClient mock that returns given responses from .post() in sequence."""
    mock = MagicMock()
    mock.post = AsyncMock(side_effect=list(responses))
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


@pytest.mark.asyncio
async def test_groq_tool_use_failed_retries_and_succeeds():
    """tool_use_failed on attempt 0 triggers one retry; second attempt succeeds."""
    from app.llm_groq import GroqLLM

    llm = object.__new__(GroqLLM)
    llm.api_key = "fake"
    llm.model = "test-model"
    llm.available = True

    fail_resp = _groq_response(400, {"error": {
        "type": "invalid_request_error", "code": "tool_use_failed", "message": "bad call",
    }})
    ok_resp = _groq_response(200, {"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    mock_client = _groq_mock_client(fail_resp, ok_resp)
    mock_settings = MagicMock(llm_connect_timeout=5, llm_read_timeout=25, groq_max_tokens=1024)

    with (
        patch("app.llm_groq.inject_security_instruction", side_effect=lambda x: x),
        patch("app.llm_groq.get_settings", return_value=mock_settings),
        patch("app.llm_groq.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await llm.chat([{"role": "user", "content": "hello"}])

    assert result["message"]["content"] == "ok"
    assert mock_client.post.call_count == 2  # retried once


@pytest.mark.asyncio
async def test_groq_tool_use_failed_retries_and_still_fails():
    """tool_use_failed on both attempts raises GroqAPIError with retried=True."""
    from app.llm_groq import GroqLLM, GroqAPIError

    llm = object.__new__(GroqLLM)
    llm.api_key = "fake"
    llm.model = "test-model"
    llm.available = True

    fail_resp = _groq_response(400, {"error": {
        "type": "invalid_request_error", "code": "tool_use_failed", "message": "still bad",
    }})

    mock_client = _groq_mock_client(fail_resp, fail_resp)
    mock_settings = MagicMock(llm_connect_timeout=5, llm_read_timeout=25, groq_max_tokens=1024)

    with (
        patch("app.llm_groq.inject_security_instruction", side_effect=lambda x: x),
        patch("app.llm_groq.get_settings", return_value=mock_settings),
        patch("app.llm_groq.httpx.AsyncClient", return_value=mock_client),
    ):
        with pytest.raises(GroqAPIError) as exc_info:
            await llm.chat([{"role": "user", "content": "hello"}])

    assert mock_client.post.call_count == 2
    err = exc_info.value
    assert err.error_code == "tool_use_failed"
    assert err.retried is True

    # Verify the chain classifies it with the "(retried)" suffix
    from app.llm_claude import _classify_error
    reason = _classify_error(err)
    assert "tool call" in reason
    assert "retried" in reason


@pytest.mark.asyncio
async def test_groq_other_400_not_retried():
    """Any 400 other than tool_use_failed is not retried; reason includes error.message."""
    from app.llm_groq import GroqLLM, GroqAPIError

    llm = object.__new__(GroqLLM)
    llm.api_key = "fake"
    llm.model = "test-model"
    llm.available = True

    fail_resp = _groq_response(400, {"error": {
        "type": "invalid_request_error",
        "code": "model_not_found",
        "message": "Model 'bad-model' does not exist.",
    }})

    mock_client = _groq_mock_client(fail_resp)
    mock_settings = MagicMock(llm_connect_timeout=5, llm_read_timeout=25, groq_max_tokens=1024)

    with (
        patch("app.llm_groq.inject_security_instruction", side_effect=lambda x: x),
        patch("app.llm_groq.get_settings", return_value=mock_settings),
        patch("app.llm_groq.httpx.AsyncClient", return_value=mock_client),
    ):
        with pytest.raises(GroqAPIError) as exc_info:
            await llm.chat([{"role": "user", "content": "hello"}])

    assert mock_client.post.call_count == 1  # no retry
    err = exc_info.value
    assert err.error_code == "model_not_found"
    assert err.retried is False
    assert "bad-model" in err.error_message

    from app.llm_claude import _classify_error
    reason = _classify_error(err)
    assert "bad-model" in reason  # error.message included in chain reason
    assert "timed out" not in reason


def test_non_timeout_error_not_labelled_as_timeout():
    """A ConnectError (not a timeout) must not be labelled 'timed out'."""
    from app.llm_claude import _classify_error
    connect_err = httpx.ConnectError("connection refused")
    result = _classify_error(connect_err, elapsed=0.1)
    assert "timed out" not in result
    assert result != "timed out"


# ── HTTP route tests ──────────────────────────────────────────────────────────


def test_no_llm_configured_returns_503(authenticated_client):
    """No LLM provider configured → HTTP 503 with error=no_llm_available."""
    fake_settings = MagicMock()
    fake_settings.any_llm_configured = False
    fake_settings.rate_limit_llm = "1000/minute"

    with patch("app.routes.chat.get_settings", return_value=fake_settings):
        resp = authenticated_client.post(
            "/api/chat/text",
            json={"message": "hi", "history": [], "tts": False},
        )

    assert resp.status_code == 503
    detail = resp.json().get("detail", {})
    assert isinstance(detail, dict), f"Expected dict detail, got: {detail!r}"
    assert detail.get("error") == "no_llm_available"
    assert "configured" in detail.get("message", "").lower()


# ── Claude two-round tool call format ────────────────────────────────────────


@pytest.mark.asyncio
async def test_claude_second_round_converts_to_anthropic_format():
    """After tool execution, _chat_claude must send Anthropic-format messages.

    chat.py stores the tool round-trip in OpenAI format (assistant tool_calls +
    role "tool") so that Groq/NVIDIA can consume it.  _chat_claude must convert
    that to Anthropic format (assistant tool_use content blocks + user
    tool_result blocks) before calling messages.create.
    """
    from app.llm_claude import ClaudeLLM

    # Second-round messages as chat.py builds them after executing set_reminder.
    messages = [
        {"role": "system", "content": "You are Athena."},
        {"role": "user", "content": "remind me to call mum at 6pm"},
        # OpenAI-format assistant message produced by _convert_claude_to_ollama_format
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "toolu_abc123",
                    "type": "function",
                    "function": {
                        "name": "set_reminder",
                        "arguments": '{"text": "Call mum", "time": "18:00"}',
                    },
                }
            ],
        },
        # OpenAI-format tool result
        {
            "role": "tool",
            "tool_call_id": "toolu_abc123",
            "content": '{"success": true, "reminder_id": 7}',
        },
    ]

    # Mock Anthropic client: capture the messages.create call and return a text reply.
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Done — reminder set for 6 PM."

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    llm = object.__new__(ClaudeLLM)
    llm.client = mock_client
    llm.settings = MagicMock(claude_model="claude-3-haiku", anthropic_api_key="fake")
    llm.available = True

    with patch("app.llm_claude.SECURITY_INSTRUCTION", ""):
        result = await llm._chat_claude(messages, tools=None, max_tokens=500)

    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    conversation = call_kwargs["messages"]

    # system is extracted; conversation must be: user / assistant / user(tool_result)
    assert len(conversation) == 3, f"Expected 3 messages, got {len(conversation)}: {conversation}"

    user_msg = conversation[0]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "remind me to call mum at 6pm"

    # Assistant message must use Anthropic tool_use content blocks, NOT OpenAI tool_calls.
    ast_msg = conversation[1]
    assert ast_msg["role"] == "assistant"
    assert isinstance(ast_msg["content"], list), "assistant content must be a list (Anthropic format)"
    assert "tool_calls" not in ast_msg, "OpenAI tool_calls key must not survive conversion"
    tool_use = ast_msg["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_use["id"] == "toolu_abc123"
    assert tool_use["name"] == "set_reminder"
    assert isinstance(tool_use["input"], dict), "input must be a dict, not a JSON string"
    assert tool_use["input"]["text"] == "Call mum"

    # Tool result must be wrapped as a user message with tool_result blocks.
    tr_msg = conversation[2]
    assert tr_msg["role"] == "user", "tool result must be role 'user' for Anthropic API"
    assert isinstance(tr_msg["content"], list)
    tr_block = tr_msg["content"][0]
    assert tr_block["type"] == "tool_result"
    assert tr_block["tool_use_id"] == "toolu_abc123"
    assert "success" in tr_block["content"]

    assert result["message"]["content"] == "Done — reminder set for 6 PM."


@pytest.mark.asyncio
async def test_convert_claude_to_ollama_format_preserves_id():
    """_convert_claude_to_ollama_format must preserve block.id so chat.py
    can pass it as tool_call_id in the second-round tool result messages."""
    from app.llm_claude import ClaudeLLM

    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.id = "toolu_xyz789"
    tool_use_block.name = "set_reminder"
    tool_use_block.input = {"text": "Buy milk", "time": "tomorrow 9am"}

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    llm = object.__new__(ClaudeLLM)
    result = llm._convert_claude_to_ollama_format(mock_response)

    tool_calls = result["message"]["tool_calls"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["id"] == "toolu_xyz789", "id must be preserved for second-round matching"
    assert tool_calls[0]["function"]["name"] == "set_reminder"


@pytest.mark.asyncio
async def test_to_anthropic_messages_plain_messages_passthrough():
    """Plain user/assistant messages (no tool use) must pass through unchanged."""
    from app.llm_claude import ClaudeLLM

    llm = object.__new__(ClaudeLLM)
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    result = llm._to_anthropic_messages(messages)
    assert result == messages


def test_providers_fail_returns_502(authenticated_client):
    """Providers configured but all fail → HTTP 502 with error=llm_providers_failed."""
    failure_response = {
        "message": {
            "role": "assistant",
            "content": "groq: invalid or unauthorized key (401); nvidia: model not found (404)",
        },
        "error": "llm_providers_failed",
    }

    fake_settings = MagicMock()
    fake_settings.any_llm_configured = True
    fake_settings.rate_limit_llm = "1000/minute"
    fake_settings.max_tool_rounds = 4

    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value=failure_response)

    with (
        patch("app.routes.chat.get_settings", return_value=fake_settings),
        patch("app.chat.pipeline.get_claude_llm", return_value=mock_llm),
        patch("app.chat.pipeline.get_memory_store", return_value=None),
        patch("app.chat.pipeline.skills_for", return_value=[]),
        patch("app.chat.pipeline.build_system_prompt", return_value="You are Athena."),
    ):
        resp = authenticated_client.post(
            "/api/chat/text",
            json={"message": "hi", "history": [], "tts": False},
        )

    assert resp.status_code == 502
    detail = resp.json().get("detail", {})
    assert isinstance(detail, dict), f"Expected dict detail, got: {detail!r}"
    assert detail.get("error") == "llm_providers_failed"
    assert "groq" in detail.get("message", "")
    assert "401" in detail.get("message", "")
