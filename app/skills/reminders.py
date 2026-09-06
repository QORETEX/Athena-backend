import json
import logging
from datetime import datetime, timezone

from dateutil import parser as dateutil_parser
from sqlalchemy import select

from app.db import Reminder, async_session
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)


async def handle_set_reminder(text: str, time: str) -> dict:
    try:
        remind_at = dateutil_parser.parse(time)
    except (ValueError, OverflowError):
        return {"success": False, "error": f"Could not parse time: {time}"}

    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone.utc)

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
        description="Create a reminder for the user at a specific date/time. The time can be ISO 8601 or natural language like 'tomorrow at 3pm'.",
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "What to remind the user about",
                },
                "time": {
                    "type": "string",
                    "description": "When to remind (ISO 8601 datetime or natural language)",
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
