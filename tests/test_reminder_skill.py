"""Tests for the set_reminder ISO 8601 time contract (Issue 2)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.skills.reminders import handle_set_reminder


# ── Valid input ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_reminder_accepts_valid_iso_with_offset():
    """A well-formed ISO 8601 datetime with UTC offset must succeed."""
    mock_reminder = MagicMock()
    mock_reminder.id = 42

    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=MagicMock(
        add=MagicMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    ))
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.skills.reminders.async_session", return_value=mock_session_cm),
        patch("app.skills.reminders.schedule_reminder", create=True),
    ):
        # Patch the session to make refresh populate reminder.id
        session_obj = MagicMock()
        session_obj.add = MagicMock()
        session_obj.commit = AsyncMock()

        async def _refresh(obj):
            obj.id = 42

        session_obj.refresh = _refresh
        mock_session_cm.__aenter__ = AsyncMock(return_value=session_obj)

        result = await handle_set_reminder(
            text="Test this tomorrow",
            time="2026-09-30T07:00:00+00:00",
        )

    assert result.get("success") is True
    assert "error" not in result or not result["error"]
    assert "remind_at" in result
    assert "+00:00" in result["remind_at"] or "Z" in result["remind_at"] or "2026-09-30" in result["remind_at"]


@pytest.mark.asyncio
async def test_set_reminder_accepts_positive_offset():
    """A datetime with a positive UTC offset (e.g. +05:00) must succeed."""
    mock_session_cm = MagicMock()
    session_obj = MagicMock()
    session_obj.add = MagicMock()
    session_obj.commit = AsyncMock()

    async def _refresh(obj):
        obj.id = 7

    session_obj.refresh = _refresh
    mock_session_cm.__aenter__ = AsyncMock(return_value=session_obj)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.skills.reminders.async_session", return_value=mock_session_cm):
        result = await handle_set_reminder(
            text="Morning standup",
            time="2026-10-02T09:00:00+05:00",
        )

    assert result.get("success") is True


# ── Invalid input ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_reminder_rejects_natural_language():
    """Natural language like 'tomorrow at 7am' must be rejected with a clear error."""
    result = await handle_set_reminder(text="Test", time="tomorrow at 7am")

    assert result.get("success") is False
    error = result.get("error", "")
    assert "ISO 8601" in error
    assert "+00:00" in error or "offset" in error.lower()


@pytest.mark.asyncio
async def test_set_reminder_rejects_naive_datetime():
    """ISO 8601 without a UTC offset must be rejected (naive datetime)."""
    result = await handle_set_reminder(text="Test", time="2026-09-30T07:00:00")

    assert result.get("success") is False
    error = result.get("error", "")
    assert "ISO 8601" in error


@pytest.mark.asyncio
async def test_set_reminder_rejects_date_only():
    """A date-only string like '2026-09-30' must be rejected."""
    result = await handle_set_reminder(text="Test", time="2026-09-30")

    assert result.get("success") is False


@pytest.mark.asyncio
async def test_set_reminder_rejects_relative_expressions():
    """Relative expressions like 'next Monday' must be rejected."""
    for bad_input in ("next Monday", "next Monday at 8am", "Friday at 9am", "3 days from now"):
        result = await handle_set_reminder(text="Test", time=bad_input)
        assert result.get("success") is False, f"Should have rejected {bad_input!r}"


@pytest.mark.asyncio
async def test_set_reminder_error_message_includes_example():
    """Error message must include a concrete ISO 8601 example."""
    result = await handle_set_reminder(text="Test", time="tomorrow at 7am")
    error = result.get("error", "")
    # Must include the example format
    assert "2026-" in error or "e.g." in error or "+00:00" in error


# ── Schema inspection ─────────────────────────────────────────────────────────


def test_set_reminder_schema_requires_iso_offset():
    """The tool schema description for 'time' must mention ISO 8601 and UTC offset."""
    from app.skills.base import get_skill

    skill = get_skill("set_reminder")
    assert skill is not None

    time_param = skill.parameters["properties"]["time"]
    desc = time_param["description"]
    assert "ISO 8601" in desc
    assert "offset" in desc.lower() or "+00:00" in desc


def test_calendar_skill_schema_requires_iso_offset():
    """create_calendar_event start_time/end_time must require ISO 8601 with offset."""
    from app.skills.base import get_skill

    skill = get_skill("create_calendar_event")
    assert skill is not None

    for param_name in ("start_time", "end_time"):
        desc = skill.parameters["properties"][param_name]["description"]
        assert "ISO 8601" in desc or "+00:00" in desc, (
            f"{param_name} description does not mention ISO 8601 offset: {desc!r}"
        )


def test_list_calendar_skill_schema_requires_iso_offset():
    """list_calendar_events start_date/end_date must require ISO 8601 with offset."""
    from app.skills.base import get_skill

    skill = get_skill("list_calendar_events")
    assert skill is not None

    for param_name in ("start_date", "end_date"):
        desc = skill.parameters["properties"][param_name]["description"]
        assert "ISO 8601" in desc or "+00:00" in desc, (
            f"{param_name} description does not mention ISO 8601 offset: {desc!r}"
        )
