from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.schemas import MessageType

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_due_reminders,
        "interval",
        seconds=30,
        id="check_due_reminders",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")


def shutdown_scheduler():
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
        scheduler = None


def schedule_reminder(reminder_id: int, remind_at: datetime, text: str):
    if scheduler is None:
        logger.warning("Scheduler not running — cannot schedule reminder %d", reminder_id)
        return
    scheduler.add_job(
        fire_reminder,
        "date",
        run_date=remind_at,
        args=[reminder_id, text],
        id=f"reminder_{reminder_id}",
        replace_existing=True,
    )
    logger.info("Scheduled reminder %d for %s", reminder_id, remind_at)


async def fire_reminder(reminder_id: int, text: str):
    from app.db import Reminder, async_session
    from app.websocket.events import broadcast_event

    try:
        async with async_session() as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder and not reminder.completed:
                reminder.completed = True
                await session.commit()
                logger.info("Reminder %d fired: %s", reminder_id, text)
    except Exception:
        logger.exception("Failed to mark reminder %d as completed", reminder_id)

    try:
        await broadcast_event(
            MessageType.REMINDER_DUE, {"text": text, "id": reminder_id}
        )
    except Exception:
        logger.exception("Failed to broadcast reminder %d", reminder_id)


async def check_due_reminders():
    from app.db import Reminder, async_session

    if async_session is None:
        return

    try:
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        async with async_session() as session:
            stmt = select(Reminder).where(
                Reminder.remind_at <= now,
                Reminder.completed == False,  # noqa: E712
            )
            result = await session.execute(stmt)
            due = result.scalars().all()

            for reminder in due:
                await fire_reminder(reminder.id, reminder.text)
    except Exception:
        logger.exception("Error checking due reminders")
