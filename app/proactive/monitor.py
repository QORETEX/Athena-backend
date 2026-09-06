from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

_monitor_task: Optional[asyncio.Task] = None
_running = False
_alerted_reminder_ids: set[int] = set()
_triggered_routine_ids: set[str] = set()

CHECK_INTERVAL_SECONDS = 60
REMINDER_LOOKAHEAD_MINUTES = 15


async def start_monitor():
    global _monitor_task, _running
    _running = True
    _monitor_task = asyncio.create_task(_monitor_loop())
    logger.info("Proactive monitor started (checking every %ds)", CHECK_INTERVAL_SECONDS)


async def stop_monitor():
    global _running, _monitor_task
    _running = False
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None
    _alerted_reminder_ids.clear()
    _triggered_routine_ids.clear()
    logger.info("Proactive monitor stopped")


async def _monitor_loop():
    while _running:
        try:
            logger.debug("Monitor cycle starting")
            await _check_upcoming_reminders()
            await _check_routine_triggers()
            logger.debug("Monitor cycle complete")
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Monitor loop error — continuing")

        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break


async def _check_upcoming_reminders():
    from app.db import Reminder, async_session as session_factory

    if session_factory is None:
        return

    now = datetime.now(timezone.utc)
    lookahead = now + timedelta(minutes=REMINDER_LOOKAHEAD_MINUTES)

    async with session_factory() as session:
        stmt = select(Reminder).where(
            and_(
                Reminder.completed == False,
                Reminder.remind_at >= now,
                Reminder.remind_at <= lookahead,
            )
        )
        result = await session.execute(stmt)
        upcoming = result.scalars().all()

    for reminder in upcoming:
        if reminder.id in _alerted_reminder_ids:
            continue

        _alerted_reminder_ids.add(reminder.id)
        minutes_until = max(1, int((reminder.remind_at - now).total_seconds() / 60))

        await push_notification(
            event_type="reminder_upcoming",
            priority="normal",
            title=f"Reminder in {minutes_until} minutes",
            body=reminder.text,
            data={"reminder_id": reminder.id, "remind_at": reminder.remind_at.isoformat()},
        )
        logger.info("Proactive alert: reminder %d in %d minutes — %s", reminder.id, minutes_until, reminder.text)


async def _check_routine_triggers():
    from app.db import Routine, async_session as session_factory

    if session_factory is None:
        return

    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        stmt = select(Routine).where(
            and_(
                Routine.enabled == True,
                Routine.trigger_type == "event",
            )
        )
        result = await session.execute(stmt)
        routines = result.scalars().all()

    for routine in routines:
        try:
            config = json.loads(routine.trigger_config)
        except (json.JSONDecodeError, TypeError):
            continue

        event_name = config.get("event")
        if not event_name:
            continue

        day_key = f"{routine.id}:{now.strftime('%Y-%m-%d')}:{event_name}"
        if day_key in _triggered_routine_ids:
            continue

        should_fire = False

        if event_name == "morning" and 6 <= now.hour <= 9:
            should_fire = True
        elif event_name == "evening" and 17 <= now.hour <= 20:
            should_fire = True
        elif event_name == "night" and 21 <= now.hour <= 23:
            should_fire = True
        elif event_name == "midday" and 11 <= now.hour <= 13:
            should_fire = True

        if should_fire:
            _triggered_routine_ids.add(day_key)

            try:
                actions = json.loads(routine.actions)
            except (json.JSONDecodeError, TypeError):
                actions = []

            await push_notification(
                event_type="routine_triggered",
                priority="low",
                title=f"Routine: {routine.name}",
                body=routine.description or f"Routine '{routine.name}' triggered by {event_name}",
                data={"routine_id": routine.id, "actions": actions, "trigger": event_name},
            )
            logger.info("Routine triggered: %s (event: %s)", routine.name, event_name)

            async with session_factory() as session:
                from sqlalchemy import update
                await session.execute(
                    update(Routine).where(Routine.id == routine.id).values(
                        last_triggered=now
                    )
                )
                await session.commit()


async def push_notification(
    event_type: str,
    priority: str,
    title: str,
    body: str,
    data: dict | None = None,
):
    from app.db import NotificationLog, async_session as session_factory
    from app.websocket.events import broadcast_event
    from app.schemas import MessageType

    if session_factory is not None:
        try:
            async with session_factory() as session:
                entry = NotificationLog(
                    event_type=event_type,
                    priority=priority,
                    title=title,
                    body=body,
                    data=json.dumps(data) if data else None,
                )
                session.add(entry)
                await session.commit()
        except Exception:
            logger.exception("Failed to log notification")

    payload = {
        "event_type": event_type,
        "priority": priority,
        "title": title,
        "body": body,
        "data": data or {},
    }

    try:
        await broadcast_event(MessageType.REMINDER_DUE, payload)
    except Exception:
        logger.exception("Failed to broadcast notification")
