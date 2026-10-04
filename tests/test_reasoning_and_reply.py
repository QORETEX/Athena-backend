"""Tests for reasoning suppression (Issue 1) and empty-reply fallback (Issue 1b)."""
from __future__ import annotations

import json

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers shared with test_llm_failures.py ─────────────────────────────────


def _groq_response(status: int, body: dict | None = None) -> httpx.Response:
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    text = json.dumps(body) if body else ""
    return httpx.Response(status, text=text, request=req)


def _groq_mock_client(*responses: httpx.Response) -> MagicMock:
    mock = MagicMock()
    mock.post = AsyncMock(side_effect=list(responses))
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


# ── Issue 1: reasoning field must never reach the client ─────────────────────


@pytest.mark.asyncio
async def test_groq_reasoning_field_not_returned_as_content():
    """When Groq returns content=null and a non-empty reasoning field, content must be ''."""
    from app.llm_groq import GroqLLM

    reasoning_text = (
        "The user wants a reminder. Let me think step by step... "
        "time parsing failed. Need to correct the time format."
    )
    response_body = {
        "choices": [{"message": {
            "role": "assistant",
            "content": None,
            "reasoning": reasoning_text,
        }}]
    }

    llm = object.__new__(GroqLLM)
    llm.api_key = "fake"
    llm.model = "test-model"
    llm.available = True

    mock_client = _groq_mock_client(_groq_response(200, response_body))
    mock_settings = MagicMock(llm_connect_timeout=5, llm_read_timeout=25, groq_max_tokens=1024)

    with (
        patch("app.llm_groq.inject_security_instruction", side_effect=lambda x: x),
        patch("app.llm_groq.get_settings", return_value=mock_settings),
        patch("app.llm_groq.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await llm.chat([{"role": "user", "content": "remind me tomorrow at 7am"}])

    content = result["message"]["content"]
    assert reasoning_text not in content, (
        f"Reasoning text leaked into content: {content!r}"
    )


@pytest.mark.asyncio
async def test_groq_reasoning_content_field_not_returned():
    """reasoning_content (alt field name) must also never reach the client."""
    from app.llm_groq import GroqLLM

    reasoning_text = "Internal chain-of-thought: step 1, step 2..."
    response_body = {
        "choices": [{"message": {
            "role": "assistant",
            "content": None,
            "reasoning_content": reasoning_text,
        }}]
    }

    llm = object.__new__(GroqLLM)
    llm.api_key = "fake"
    llm.model = "test-model"
    llm.available = True

    mock_client = _groq_mock_client(_groq_response(200, response_body))
    mock_settings = MagicMock(llm_connect_timeout=5, llm_read_timeout=25, groq_max_tokens=1024)

    with (
        patch("app.llm_groq.inject_security_instruction", side_effect=lambda x: x),
        patch("app.llm_groq.get_settings", return_value=mock_settings),
        patch("app.llm_groq.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await llm.chat([{"role": "user", "content": "hi"}])

    content = result["message"]["content"]
    assert reasoning_text not in content


@pytest.mark.asyncio
async def test_groq_real_content_still_returned():
    """When message.content is present, it must be returned unchanged."""
    from app.llm_groq import GroqLLM

    real_content = "Reminder set for tomorrow at 7 AM."
    response_body = {
        "choices": [{"message": {
            "role": "assistant",
            "content": real_content,
            "reasoning": "some internal reasoning",
        }}]
    }

    llm = object.__new__(GroqLLM)
    llm.api_key = "fake"
    llm.model = "test-model"
    llm.available = True

    mock_client = _groq_mock_client(_groq_response(200, response_body))
    mock_settings = MagicMock(llm_connect_timeout=5, llm_read_timeout=25, groq_max_tokens=1024)

    with (
        patch("app.llm_groq.inject_security_instruction", side_effect=lambda x: x),
        patch("app.llm_groq.get_settings", return_value=mock_settings),
        patch("app.llm_groq.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await llm.chat([{"role": "user", "content": "remind me tomorrow at 7am"}])

    assert result["message"]["content"] == real_content


# ── Issue 1b: empty reply after tool loop ─────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_reply_after_tool_loop_uses_summary():
    """Post-tool round returns empty content → summary used immediately (2 LLM calls total)."""
    from app.chat.pipeline import run_chat_turn

    call_count = 0
    tool_result = {"success": True, "reminder_id": 1, "remind_at": "2026-09-30T07:00:00+00:00"}

    async def mock_chat(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": "tc1",
                "function": {"name": "set_reminder", "arguments": {
                    "text": "test this", "time": "2026-09-30T07:00:00+00:00",
                }},
            }]}}
        else:
            # Post-tool response: empty content — bounded loop uses summary directly
            return {"message": {"role": "assistant", "content": ""}}

    mock_llm = MagicMock()
    mock_llm.chat = mock_chat

    mock_skill = MagicMock()
    mock_skill.client_executed = False
    mock_skill.returns_external_content = False

    with (
        patch("app.chat.pipeline.get_claude_llm", return_value=mock_llm),
        patch("app.chat.pipeline.get_memory_store", return_value=None),
        patch("app.chat.pipeline.skills_for", return_value=[]),
        patch("app.chat.pipeline.get_skill", return_value=mock_skill),
        patch("app.chat.pipeline.build_system_prompt", return_value="You are Athena."),
        patch("app.chat.pipeline.call_skill_handler", new=AsyncMock(return_value=tool_result)),
    ):
        result = await run_chat_turn(
            "Remind me to test this tomorrow at 7am", []
        )

    assert call_count == 2, f"Expected 2 LLM calls, got {call_count}"
    assert "Reminder set for" in result.reply
    assert "Wed" in result.reply
    assert result.error is None


@pytest.mark.asyncio
async def test_empty_reply_fallback_summary_when_post_tool_empty():
    """Post-tool round returns empty → summary from tool results (2 LLM calls, not 3)."""
    from app.chat.pipeline import run_chat_turn

    call_count = 0
    tool_result = {"success": True, "reminder_id": 2, "remind_at": "2026-10-02T09:00:00+00:00"}

    async def mock_chat(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": "tc2",
                "function": {"name": "set_reminder", "arguments": {
                    "text": "submit assignment", "time": "2026-10-02T09:00:00+00:00",
                }},
            }]}}
        else:
            return {"message": {"role": "assistant", "content": ""}}

    mock_llm = MagicMock()
    mock_llm.chat = mock_chat

    mock_skill = MagicMock()
    mock_skill.client_executed = False
    mock_skill.returns_external_content = False

    with (
        patch("app.chat.pipeline.get_claude_llm", return_value=mock_llm),
        patch("app.chat.pipeline.get_memory_store", return_value=None),
        patch("app.chat.pipeline.skills_for", return_value=[]),
        patch("app.chat.pipeline.get_skill", return_value=mock_skill),
        patch("app.chat.pipeline.build_system_prompt", return_value="You are Athena."),
        patch("app.chat.pipeline.call_skill_handler", new=AsyncMock(return_value=tool_result)),
    ):
        result = await run_chat_turn(
            "Remind me on Friday at 9am to submit my assignment", []
        )

    assert call_count == 2, f"Expected 2 LLM calls, got {call_count}"
    # Summary fallback must mention the reminder was set and include the date
    assert "Reminder set for" in result.reply
    assert "Fri" in result.reply
    assert result.error is None


# ── _summarize_tool_results unit tests ────────────────────────────────────────


def test_summarize_reminder_result():
    """set_reminder success produces a human-readable date string."""
    from app.chat.pipeline import _summarize_tool_results

    results = [{"tool": "set_reminder", "result": {
        "success": True, "reminder_id": 1, "remind_at": "2026-09-30T07:00:00+00:00",
    }}]
    summary = _summarize_tool_results(results)
    assert "Reminder set for" in summary
    assert "Wed" in summary
    assert "30" in summary
    assert "Sep" in summary


def test_summarize_error_result():
    """A tool result with error must include the error text."""
    from app.chat.pipeline import _summarize_tool_results

    results = [{"tool": "set_reminder", "result": {
        "success": False, "error": "time must be ISO 8601 with UTC offset",
    }}]
    summary = _summarize_tool_results(results)
    assert "Error:" in summary


def test_summarize_empty_results():
    """Empty tool_results list returns 'Done.'"""
    from app.chat.pipeline import _summarize_tool_results
    assert _summarize_tool_results([]) == "Done."
