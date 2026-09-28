"""Tests for LLM failure reporting — no real network calls."""
from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a real HTTPStatusError with the given status code."""
    req = httpx.Request("POST", "https://example.com")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError("", request=req, response=resp)


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
    assert _classify_error(httpx.TimeoutException("timed out")) == "timed out"


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

    mock_settings = MagicMock()
    mock_settings.ollama_enabled = False

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

    mock_settings = MagicMock()
    mock_settings.ollama_enabled = False

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

    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value=failure_response)

    with (
        patch("app.routes.chat.get_settings", return_value=fake_settings),
        patch("app.routes.chat.get_claude_llm", return_value=mock_llm),
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
