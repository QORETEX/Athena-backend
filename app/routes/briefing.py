from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import (
    BackgroundTask,
    Reminder,
    SmartHomeDevice,
    get_db,
)
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


async def generate_briefing(db: Optional[AsyncSession] = None) -> dict:
    """Generate a comprehensive briefing. Can be called from routes or routines."""
    from app.db import async_session as session_factory

    own_session = False
    if db is None and session_factory is not None:
        db = session_factory()
        own_session = True

    briefing = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weather": None,
        "reminders": [],
        "devices": [],
        "pending_tasks": [],
        "system_health": {},
    }

    try:
        # ── Weather ────────────────────────────────────
        try:
            from app.routes.preferences import get_user_preferences
            prefs = await get_user_preferences()
            location = prefs.get("location")

            from app.skills.weather import handle_weather
            if location:
                briefing["weather"] = await handle_weather(location=location)
            else:
                briefing["weather"] = await handle_weather()
        except Exception as e:
            logger.warning("Briefing: weather failed — %s", e)
            briefing["weather"] = {"error": str(e)}

        if db is not None:
            # ── Today's reminders ──────────────────────────
            try:
                now = datetime.now(timezone.utc)
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = start_of_day + timedelta(days=1)

                result = await db.execute(
                    select(Reminder).where(
                        and_(
                            Reminder.completed == False,
                            Reminder.remind_at >= start_of_day,
                            Reminder.remind_at < end_of_day,
                        )
                    ).order_by(Reminder.remind_at)
                )
                reminders = result.scalars().all()
                briefing["reminders"] = [
                    {
                        "id": r.id,
                        "text": r.text,
                        "remind_at": r.remind_at.isoformat(),
                    }
                    for r in reminders
                ]
            except Exception as e:
                logger.warning("Briefing: reminders failed — %s", e)

            # ── Smart home devices ─────────────────────────
            try:
                result = await db.execute(
                    select(SmartHomeDevice).order_by(SmartHomeDevice.room, SmartHomeDevice.name)
                )
                devices = result.scalars().all()
                briefing["devices"] = [
                    {
                        "name": d.name,
                        "device_type": d.device_type,
                        "room": d.room,
                        "is_favorite": d.is_favorite,
                    }
                    for d in devices
                ]
            except Exception as e:
                logger.warning("Briefing: devices failed — %s", e)

            # ── Pending background tasks ───────────────────
            try:
                result = await db.execute(
                    select(BackgroundTask).where(
                        BackgroundTask.status.in_(["pending", "running"])
                    )
                )
                tasks = result.scalars().all()
                briefing["pending_tasks"] = [
                    {
                        "id": t.id,
                        "task_type": t.task_type,
                        "prompt": t.prompt[:100],
                        "status": t.status,
                    }
                    for t in tasks
                ]
            except Exception as e:
                logger.warning("Briefing: tasks failed — %s", e)

        # ── System health ──────────────────────────────
        try:
            health = {}
            try:
                from app.websocket.voice import WHISPER_AVAILABLE
                health["stt"] = WHISPER_AVAILABLE
            except ImportError:
                health["stt"] = False
            try:
                from app.websocket.voice import PIPER_AVAILABLE
                health["tts"] = PIPER_AVAILABLE
            except ImportError:
                health["tts"] = False
            try:
                from app.websocket.voice import VAD_AVAILABLE
                health["vad"] = VAD_AVAILABLE
            except ImportError:
                health["vad"] = False
            try:
                from app.memory.store import get_memory_store
                health["memory"] = get_memory_store() is not None
            except ImportError:
                health["memory"] = False
            try:
                from app.skills.image_gen import GEMINI_AVAILABLE
                health["image_gen"] = GEMINI_AVAILABLE
            except ImportError:
                health["image_gen"] = False

            briefing["system_health"] = health
        except Exception as e:
            logger.warning("Briefing: health check failed — %s", e)

    finally:
        if own_session and db is not None:
            await db.close()

    return briefing


# ── Routes ────────────────────────────────────────────────


@router.get("/")
async def get_briefing(db: AsyncSession = Depends(get_db)):
    """Generate a comprehensive daily briefing."""
    return await generate_briefing(db=db)


@router.get("/summary")
async def get_briefing_summary(db: AsyncSession = Depends(get_db)):
    """Generate a natural language summary of the briefing via Ollama."""
    briefing = await generate_briefing(db=db)

    try:
        from app.llm import chat_with_tools
        from app.routes.preferences import get_user_preferences

        prefs = await get_user_preferences()
        user_name = prefs.get("preferred_name", "")
        address = f" {user_name}" if user_name else ""

        now = datetime.now(timezone.utc)
        hour = now.hour
        if 5 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 17:
            period = "afternoon"
        elif 17 <= hour < 21:
            period = "evening"
        else:
            period = "night"

        import json
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Athena, a personal AI assistant. Generate a natural, spoken briefing "
                    "from the following data. Be concise and warm — this will be read aloud. "
                    "Start with a greeting appropriate for the time of day. "
                    "Cover weather first, then reminders, then anything notable. "
                    "Skip sections with no data. Keep it under 150 words."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Time of day: {period}\n"
                    f"User's name: {user_name or 'not set'}\n\n"
                    f"Briefing data:\n{json.dumps(briefing, indent=2, default=str)}"
                ),
            },
        ]

        resp = await chat_with_tools(messages)
        summary = resp.get("message", {}).get("content", "")

        if not summary or "error" in resp:
            summary = f"Good {period}{address}. I have your briefing ready but couldn't generate a spoken summary right now."

        return {"summary": summary, "briefing": briefing}

    except Exception as e:
        logger.exception("Briefing summary generation failed")
        return {
            "summary": "Your briefing is ready, but I couldn't generate a spoken summary.",
            "briefing": briefing,
            "error": str(e),
        }


# ── Skill registration ────────────────────────────────────


async def handle_daily_briefing() -> dict:
    return await generate_briefing()


register_skill(
    Skill(
        name="daily_briefing",
        description=(
            "Generate and deliver a daily briefing covering weather, reminders, "
            "smart home status, and system health. Use when the user asks for a "
            "briefing, status update, or 'what's going on today'."
        ),
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=handle_daily_briefing,
        timeout=30,
    )
)
