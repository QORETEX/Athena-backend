"""Tests for bounded tool loop in run_chat_turn and Groq tool_choice-none fix."""
from __future__ import annotations

import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.skills.base import SkillInfo


# ── helpers ────────────────────────────────────────────────────────────────────


def _groq_response(status: int, body: dict | None = None) -> httpx.Response:
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return httpx.Response(status, text=json.dumps(body) if body else "", request=req)


def _list_reminders_skill(handler=None):
    mock = MagicMock()
    mock.client_executed = False
    mock.handler = handler or AsyncMock(return_value={"reminders": []})
    mock.timeout = 30.0
    mock.returns_external_content = False
    mock.parameters = {"type": "object", "properties": {}}
    mock.name = "list_reminders"
    mock.enabled_check = None
    return mock


def _list_reminders_skill_info() -> SkillInfo:
    return SkillInfo(
        name="list_reminders",
        summary="List reminders",
        description="List upcoming reminders.",
        parameters={"type": "object", "properties": {}},
        client_executed=False,
        available=True,
        unavailable_reason=None,
    )


def _tc(name, args=None, tc_id=None):
    entry = {"function": {"name": name, "arguments": args or {}}}
    if tc_id:
        entry["id"] = tc_id
    return entry


# ── Bounded loop: tool error then correct call ────────────────────────────────


@pytest.mark.asyncio
async def test_tool_error_then_correct_call_produces_reply():
    """Round 0: empty-key args → error result. Round 1: correct call → success. Round 2: text reply."""
    from app.chat.pipeline import run_chat_turn

    call_count = 0
    handler_call_count = 0

    async def fake_handler():
        nonlocal handler_call_count
        handler_call_count += 1
        return {"reminders": []}

    skill = _list_reminders_skill(handler=fake_handler)

    async def mock_chat(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Model calls list_reminders with empty-key arg (the bug scenario)
            return {"message": {"role": "assistant", "content": "", "tool_calls": [
                _tc("list_reminders", {"": "bad_value"}, "tc1"),
            ]}}
        elif call_count == 2:
            # Model tries again correctly
            return {"message": {"role": "assistant", "content": "", "tool_calls": [
                _tc("list_reminders", {}, "tc2"),
            ]}}
        else:
            return {"message": {"role": "assistant", "content": "You have no reminders."}}

    mock_llm = MagicMock()
    mock_llm.chat = mock_chat

    with (
        patch("app.chat.pipeline.get_claude_llm", return_value=mock_llm),
        patch("app.chat.pipeline.get_memory_store", return_value=None),
        patch("app.chat.pipeline.skills_for", return_value=[_list_reminders_skill_info()]),
        patch("app.chat.pipeline.get_skill", return_value=skill),
        patch("app.chat.pipeline.build_system_prompt", return_value="You are Athena."),
        patch("app.chat.pipeline.call_skill_handler", new=AsyncMock(return_value={"reminders": []})) as mock_dispatch,
    ):
        result = await run_chat_turn("What reminders do I have?", [])

    assert result.error is None
    assert result.reply == "You have no reminders."
    assert call_count == 3
    # call_skill_handler must have been called twice (once per tool round)
    assert mock_dispatch.call_count == 2


@pytest.mark.asyncio
async def test_tool_loop_capped_at_max_rounds():
    """After max_tool_rounds the loop forces a text-only call; summary used if still no text."""
    from app.chat.pipeline import run_chat_turn

    call_count = 0

    async def mock_chat(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if tools:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [
                _tc("list_reminders", {}, f"tc{call_count}"),
            ]}}
        # Final round (tools=None): model returns tool call anyway — should trigger summary
        return {"message": {"role": "assistant", "content": "", "tool_calls": [
            _tc("list_reminders", {}, "tc_final"),
        ]}}

    mock_llm = MagicMock()
    mock_llm.chat = mock_chat

    skill = _list_reminders_skill(
        handler=AsyncMock(return_value={"reminders": [{"id": 1, "text": "Buy milk", "remind_at": "2026-10-01T08:00:00+00:00"}]})
    )

    mock_settings = MagicMock()
    mock_settings.max_tool_rounds = 2

    with (
        patch("app.chat.pipeline.get_claude_llm", return_value=mock_llm),
        patch("app.chat.pipeline.get_memory_store", return_value=None),
        patch("app.chat.pipeline.skills_for", return_value=[_list_reminders_skill_info()]),
        patch("app.chat.pipeline.get_skill", return_value=skill),
        patch("app.chat.pipeline.build_system_prompt", return_value="You are Athena."),
        patch("app.chat.pipeline.call_skill_handler", new=AsyncMock(return_value={
            "reminders": [{"id": 1, "text": "Buy milk", "remind_at": "2026-10-01T08:00:00+00:00"}]
        })),
        patch("app.chat.pipeline.get_settings", return_value=mock_settings),
    ):
        result = await run_chat_turn("What reminders do I have?", [])

    assert result.error is None
    assert result.reply  # must get a reply (summary fallback)
    # Tool calls must be capped at max_tool_rounds (2)
    assert len(result.tool_calls) <= 2
    # Final call was text-only (call_count = max_rounds + 1 = 3)
    assert call_count == 3


@pytest.mark.asyncio
async def test_providers_failed_after_tools_uses_summary():
    """If providers fail after tools ran, summary is returned not an error."""
    from app.chat.pipeline import run_chat_turn

    call_count = 0

    async def mock_chat(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [
                _tc("list_reminders", {}, "tc1"),
            ]}}
        # Second call fails with providers_failed
        return {
            "message": {"role": "assistant", "content": "all failed"},
            "error": "llm_providers_failed",
        }

    mock_llm = MagicMock()
    mock_llm.chat = mock_chat

    with (
        patch("app.chat.pipeline.get_claude_llm", return_value=mock_llm),
        patch("app.chat.pipeline.get_memory_store", return_value=None),
        patch("app.chat.pipeline.skills_for", return_value=[_list_reminders_skill_info()]),
        patch("app.chat.pipeline.get_skill", return_value=_list_reminders_skill()),
        patch("app.chat.pipeline.build_system_prompt", return_value="You are Athena."),
        patch("app.chat.pipeline.call_skill_handler", new=AsyncMock(return_value={"reminders": []})),
    ):
        result = await run_chat_turn("What reminders do I have?", [])

    # Must not surface llm_providers_failed; must return a summary instead
    assert result.error is None
    assert result.reply  # summary "You have no upcoming reminders." or similar


# ── Groq: tool_choice-none not retried ────────────────────────────────────────


@pytest.mark.asyncio
async def test_groq_tool_choice_none_not_retried():
    """'Tool choice is none, but model called a tool' must NOT trigger a retry attempt."""
    from app.llm_groq import GroqLLM, GroqAPIError

    error_body = {
        "error": {
            "type": "invalid_request_error",
            "code": "tool_use_failed",
            "message": "Tool choice is none, but model called a tool",
        }
    }

    llm = object.__new__(GroqLLM)
    llm.api_key = "fake"
    llm.model = "test-model"
    llm.available = True

    http_call_count = 0

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, *a, **kw):
            nonlocal http_call_count
            http_call_count += 1
            r = _groq_response(400, error_body)
            raise httpx.HTTPStatusError("400", request=r.request, response=r)

    mock_settings = MagicMock(llm_connect_timeout=5, llm_read_timeout=25, groq_max_tokens=1024)

    with (
        patch("app.llm_groq.inject_security_instruction", side_effect=lambda x: x),
        patch("app.llm_groq.get_settings", return_value=mock_settings),
        patch("app.llm_groq.httpx.AsyncClient", return_value=FakeClient()),
    ):
        with pytest.raises(GroqAPIError) as exc_info:
            await llm.chat([{"role": "user", "content": "hi"}])

    assert http_call_count == 1, f"Expected 1 HTTP call (no retry), got {http_call_count}"
    assert exc_info.value.error_code == "tool_use_failed"


@pytest.mark.asyncio
async def test_groq_malformed_tool_call_still_retried():
    """A genuine malformed-tool-call error (not tool_choice-none) still retries once."""
    from app.llm_groq import GroqLLM, GroqAPIError

    malformed_body = {
        "error": {
            "type": "invalid_request_error",
            "code": "tool_use_failed",
            "message": "Tool call arguments are not valid JSON",
        }
    }
    success_body = {
        "choices": [{"message": {"role": "assistant", "content": "Hello", "tool_calls": []}}]
    }

    llm = object.__new__(GroqLLM)
    llm.api_key = "fake"
    llm.model = "test-model"
    llm.available = True

    http_call_count = 0

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, *a, **kw):
            nonlocal http_call_count
            http_call_count += 1
            if http_call_count == 1:
                r = _groq_response(400, malformed_body)
                raise httpx.HTTPStatusError("400", request=r.request, response=r)
            # Second attempt succeeds
            return _groq_response(200, success_body)

    mock_settings = MagicMock(llm_connect_timeout=5, llm_read_timeout=25, groq_max_tokens=1024)

    with (
        patch("app.llm_groq.inject_security_instruction", side_effect=lambda x: x),
        patch("app.llm_groq.get_settings", return_value=mock_settings),
        patch("app.llm_groq.httpx.AsyncClient", return_value=FakeClient()),
    ):
        result = await llm.chat([{"role": "user", "content": "hi"}])

    assert http_call_count == 2, f"Expected 2 HTTP calls (one retry), got {http_call_count}"
    assert result["message"]["content"] == "Hello"
