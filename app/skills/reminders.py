import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import Reminder, async_session
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)

_ISO_EXAMPLE = "2026-09-30T07:00:00+00:00"
_TIME_ERROR = (
    f"time must be ISO 8601 with UTC offset, e.g. {_ISO_EXAMPLE}. "
    "Use the current date and the '14 days' calendar in the system prompt to "
    "compute the correct date, then append the UTC offset."
)


async def handle_set_reminder(text: str, time: str) -> dict:
    try:
        remind_at = datetime.fromisoformat(time)
    except (ValueError, OverflowError):
        return {"success": False, "error": _TIME_ERROR}

    if remind_at.tzinfo is None:
        return {"success": False, "error": _TIME_ERROR}

    reminder = Reminder(text=text, remind_at=remind_at)
    async with async_session() as session:
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)

    try:
        from app.scheduler import schedule_reminder

        schedule_reminder(reminder.id, remind_at, text)
    except Exception as e:
        logger.warning("Could not schedule reminder %d: %s", reminder.id, e)

    return {
        "success": True,
        "reminder_id": reminder.id,
        "remind_at": remind_at.isoformat(),
    }


async def handle_list_reminders() -> dict:
    async with async_session() as session:
        result = await session.execute(
            select(Reminder)
            .where(Reminder.completed == False)
            .order_by(Reminder.remind_at)
            .limit(20)
        )
        reminders = result.scalars().all()

    return {
        "reminders": [
            {
                "id": r.id,
                "text": r.text,
                "remind_at": r.remind_at.isoformat(),
            }
            for r in reminders
        ]
    }


register_skill(
    Skill(
        name="set_reminder",
        description="Create a reminder for the user at a specific date/time.",
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "What to remind the user about",
                },
                "time": {
                    "type": "string",
                    "description": (
                        "When to remind — ISO 8601 datetime with UTC offset "
                        "(e.g. 2026-09-30T07:00:00+00:00). "
                        "Use the '14 days' calendar in the system prompt to look up "
                        "the exact date for relative expressions like 'tomorrow' or "
                        "'next Friday', then append the UTC offset."
                    ),
                },
            },
            "required": ["text", "time"],
        },
        handler=handle_set_reminder,
    )
)

register_skill(
    Skill(
        name="list_reminders",
        description="List upcoming (not yet completed) reminders for the user.",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=handle_list_reminders,
    )
)
