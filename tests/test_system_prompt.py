"""Tests for system prompt generation — date/time, capabilities, memory honesty."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.llm import _format_14_day_calendar, _format_current_time, build_system_prompt


# ── _format_current_time ──────────────────────────────────────────────────────


def test_format_current_time_weekday_and_date():
    """_format_current_time must include the correct weekday, day, month, and year."""
    # 2026-09-29 is a Tuesday
    fake = datetime(2026, 9, 29, 11, 54, 0, tzinfo=timezone.utc)
    result = _format_current_time(fake)
    assert "Tuesday" in result
    assert "29" in result
    assert "September" in result
    assert "2026" in result
    assert "11:54" in result


def test_format_current_time_utc_offset():
    """UTC timezone must show UTC+00:00 in the output."""
    fake = datetime(2026, 9, 29, 8, 0, 0, tzinfo=timezone.utc)
    result = _format_current_time(fake)
    assert "UTC+00:00" in result


def test_format_current_time_different_days():
    """Different input dates must produce different output strings."""
    tuesday = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    wednesday = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    assert _format_current_time(tuesday) != _format_current_time(wednesday)
    assert "Tuesday" in _format_current_time(tuesday)
    assert "Wednesday" in _format_current_time(wednesday)


# ── build_system_prompt — current time ────────────────────────────────────────


def test_build_system_prompt_includes_current_time():
    """build_system_prompt must embed the output of _format_current_time each call."""
    sentinel = "Tuesday 29 September 2026, 11:54 (UTC, UTC+00:00)"
    with patch("app.llm._format_current_time", return_value=sentinel) as mock_fmt:
        prompt = build_system_prompt()
    mock_fmt.assert_called_once()
    assert sentinel in prompt


def test_build_system_prompt_not_cached():
    """Two successive calls with different injected times must differ in the prompt."""
    t1 = "Tuesday 29 September 2026, 10:00 (UTC, UTC+00:00)"
    t2 = "Wednesday 30 September 2026, 10:00 (UTC, UTC+00:00)"

    with patch("app.llm._format_current_time", return_value=t1):
        prompt1 = build_system_prompt()

    with patch("app.llm._format_current_time", return_value=t2):
        prompt2 = build_system_prompt()

    assert t1 in prompt1
    assert t2 in prompt2
    assert t1 not in prompt2


# ── build_system_prompt — capabilities ────────────────────────────────────────


# Descriptions used in helper tools — must match what the real skills expose
# so that capability assertions check the right concepts.
_SKILL_DESCS: dict[str, str] = {
    "set_reminder": "Set a reminder for a specific date and time.",
    "list_reminders": "List upcoming reminders.",
    "get_weather": "Get current weather and forecast for a location.",
    "save_note": "Save a note for the user.",
    "search_notes": "Search the user's saved notes by keyword.",
    "delete_note": "Delete a specific note by ID.",
    "control_smart_device": "Control a smart home device via Home Assistant.",
    "web_search": "Search the web for current information using SearXNG.",
    "generate_image": "Generate an image from a text description.",
    "list_calendar_events": "List upcoming events from the user's device calendar.",
    "create_calendar_event": "Create a new event on the user's device calendar.",
    "daily_briefing": "Generate and deliver a daily briefing.",
    "background_research": "Submit a research task to run in the background.",
}


def _make_tool(name: str, desc: str | None = None) -> dict:
    description = desc if desc is not None else _SKILL_DESCS.get(name, f"Use {name}.")
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {}}}


def _extract_capabilities(prompt: str) -> str:
    """Return the full capabilities block (empty string if absent)."""
    marker = "Capabilities available this session:\n"
    if marker not in prompt:
        return ""
    after = prompt.split(marker, 1)[1]
    # Block ends at blank line
    end = after.find("\n\n")
    return after[:end] if end >= 0 else after


def test_capabilities_from_available_tools():
    """Capabilities block must reflect only the tools in available_tools."""
    tools = [_make_tool("set_reminder"), _make_tool("get_weather")]
    prompt = build_system_prompt(available_tools=tools)
    cap = _extract_capabilities(prompt)
    assert cap, "capabilities block missing"
    assert "reminder" in cap
    assert "weather" in cap
    # These are not in the tool list — must not appear in the capabilities block
    assert "smart home" not in cap
    assert "SearXNG" not in cap
    assert "image" not in cap


def test_capabilities_omits_disabled_features():
    """Smart home, web search, and image gen must not appear in the capabilities block."""
    tools = [_make_tool("save_note"), _make_tool("set_reminder")]
    prompt = build_system_prompt(available_tools=tools)
    cap = _extract_capabilities(prompt)
    assert "smart home" not in cap
    assert "SearXNG" not in cap
    assert "image" not in cap
    assert "note" in cap
    assert "reminder" in cap


def test_capabilities_empty_tool_list():
    """An empty available_tools list must produce the 'no capabilities' notice."""
    prompt = build_system_prompt(available_tools=[])
    assert "No tool capabilities are available" in prompt


def test_capabilities_calendar_only_when_in_tools():
    """Calendar tools must only appear in the prompt when they are in available_tools."""
    with_cal = [_make_tool("list_calendar_events"), _make_tool("set_reminder")]
    without_cal = [_make_tool("set_reminder")]

    prompt_with = build_system_prompt(available_tools=with_cal)
    prompt_without = build_system_prompt(available_tools=without_cal)

    assert "calendar" in prompt_with
    assert "calendar" not in prompt_without


# ── build_system_prompt — memory honesty ─────────────────────────────────────


def test_memory_unavailable_adds_disclaimer():
    """When memory_available=False the prompt must say not to promise persistence."""
    prompt = build_system_prompt(memory_available=False)
    assert "Long-term memory is not available" in prompt


def test_memory_available_no_disclaimer():
    """When memory_available=True the memory-unavailable disclaimer must be absent."""
    prompt = build_system_prompt(memory_available=True)
    assert "Long-term memory is not available" not in prompt


# ── _format_14_day_calendar ───────────────────────────────────────────────────


def test_format_14_day_calendar_has_14_entries():
    """Calendar must contain exactly 14 comma-separated entries."""
    fake = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    cal = _format_14_day_calendar(fake)
    entries = [e.strip() for e in cal.split(",")]
    assert len(entries) == 14


def test_format_14_day_calendar_starts_with_today():
    """First entry must be today (Tue 29 Sep for 2026-09-29)."""
    fake = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    cal = _format_14_day_calendar(fake)
    assert cal.startswith("Tue 29 Sep")


def test_format_14_day_calendar_crosses_month_boundary():
    """Calendar must correctly cross from September into October."""
    fake = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    cal = _format_14_day_calendar(fake)
    # September tail
    assert "Wed 30 Sep" in cal
    # October head
    assert "Thu 1 Oct" in cal
    assert "Fri 2 Oct" in cal


def test_format_14_day_calendar_oct3_is_saturday():
    """3 October 2026 must appear as Saturday — this was the wrong-weekday bug."""
    fake = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    cal = _format_14_day_calendar(fake)
    assert "Sat 3 Oct" in cal
    assert "Sun 3 Oct" not in cal


def test_format_14_day_calendar_ends_on_14th_day():
    """Last entry must be 13 days after today (Mon 12 Oct for 2026-09-29)."""
    fake = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    cal = _format_14_day_calendar(fake)
    assert cal.rstrip().endswith("Mon 12 Oct")


def test_build_system_prompt_includes_calendar():
    """build_system_prompt must embed the 14-day calendar with correct weekdays."""
    fake = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    prompt = build_system_prompt(_now=fake)
    assert "Sat 3 Oct" in prompt
    assert "Thu 1 Oct" in prompt
    assert "Mon 5 Oct" in prompt


def test_build_system_prompt_calendar_not_cached():
    """Two calls with different frozen times must produce different calendars."""
    t1 = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
    p1 = build_system_prompt(_now=t1)
    p2 = build_system_prompt(_now=t2)
    assert "Tue 29 Sep" in p1
    assert "Tue 29 Sep" not in p2
    assert "Thu 1 Oct" in p2
