"""Tests for service reachability gating on URL-based skills."""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure web_search is registered before any test in this file runs.
import app.skills.web_search  # noqa: F401


@pytest.fixture(autouse=True)
def reset_reachability():
    """Restore av._reachable to its pre-test state after each test."""
    import app.availability as av
    saved = dict(av._reachable)
    yield
    av._reachable.clear()
    av._reachable.update(saved)


def test_unreachable_searxng_not_offered():
    """web_search must not appear in server tools when SearXNG is unreachable."""
    import app.availability as av
    from app.skills.base import get_server_tools

    av._reachable["web_search"] = False

    fake_s = MagicMock()
    fake_s.web_search_enabled = True

    with patch("app.skills.web_search.get_settings", return_value=fake_s):
        tools = get_server_tools()

    names = {t["function"]["name"] for t in tools}
    assert "web_search" not in names, "web_search must not be offered when unreachable"


def test_reachable_searxng_offered():
    """web_search must appear in server tools when SearXNG is reachable."""
    import app.availability as av
    from app.skills.base import get_server_tools

    av._reachable["web_search"] = True

    fake_s = MagicMock()
    fake_s.web_search_enabled = True

    with patch("app.skills.web_search.get_settings", return_value=fake_s):
        tools = get_server_tools()

    names = {t["function"]["name"] for t in tools}
    assert "web_search" in names, "web_search must be offered when reachable"


@pytest.mark.asyncio
async def test_runtime_connect_error_marks_unreachable():
    """A ConnectError during handle_web_search must immediately mark the service unreachable."""
    import app.availability as av
    from app.skills.web_search import handle_web_search

    av._reachable["web_search"] = True  # start reachable

    fake_s = MagicMock()
    fake_s.web_search_enabled = True
    fake_s.searxng_url = "http://localhost:8080"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.skills.web_search.get_settings", return_value=fake_s),
        patch("httpx.AsyncClient", return_value=mock_cm),
    ):
        result = await handle_web_search("test query")

    assert "error" in result
    assert av._reachable.get("web_search") is False, (
        "web_search must be marked unreachable after a ConnectError"
    )


def test_system_prompt_no_web_search_text_when_not_offered():
    """The capabilities block must contain no web-search or reminder text when those skills are absent."""
    from app.llm import build_system_prompt

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather and forecast for a location.",
                "parameters": {},
            },
        }
    ]
    prompt = build_system_prompt(available_tools=tools)

    # Verify the capabilities block only
    marker = "Capabilities available this session:\n"
    assert marker in prompt, "capabilities block missing"
    cap_block = prompt.split(marker, 1)[1].split("\n\n")[0]

    assert "SearXNG" not in cap_block
    assert "web" not in cap_block.lower()
    assert "reminder" not in cap_block.lower()
    # Weather must be present (the offered skill)
    assert "weather" in cap_block.lower()
