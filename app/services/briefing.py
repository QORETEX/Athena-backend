"""
Morning/Evening Briefing Service - Daily summaries for JARVIS
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from app.db import async_session, Reminder, Note, Meeting
from app.llm_claude import get_claude_llm

logger = logging.getLogger(__name__)


class BriefingService:
    """Generate intelligent daily briefings"""

    async def generate_morning_briefing(self) -> dict:
        """
        Generate comprehensive morning briefing

        Returns formatted briefing with:
        - Calendar overview
        - Weather
        - Reminders
        - Important notes
        - Priorities
        """
        now = datetime.now(timezone.utc)
        today_end = now.replace(hour=23, minute=59, second=59)

        # Gather data
        calendar = await self._get_todays_meetings()
        reminders = await self._get_todays_reminders()
        recent_notes = await self._get_recent_notes()
        weather = await self._get_weather_summary()

        # Generate briefing with Claude
        briefing_text = await self._generate_briefing_text(
            calendar, reminders, recent_notes, weather, "morning"
        )

        return {
            "type": "morning",
            "generated_at": now.isoformat(),
            "calendar_count": len(calendar),
            "reminders_count": len(reminders),
            "briefing": briefing_text,
            "details": {
                "calendar": calendar,
                "reminders": reminders,
                "notes": recent_notes,
                "weather": weather
            }
        }

    async def generate_evening_briefing(self) -> dict:
        """
        Generate evening briefing

        Returns formatted briefing with:
        - Day summary
        - Tomorrow's schedule
        - Completed tasks
        - Prep for tomorrow
        """
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)

        # Gather data
        tomorrow_meetings = await self._get_meetings_between(tomorrow, tomorrow_end)
        completed_reminders = await self._get_completed_reminders_today()
        tomorrow_reminders = await self._get_reminders_between(tomorrow, tomorrow_end)

        briefing_text = await self._generate_briefing_text(
            tomorrow_meetings, tomorrow_reminders, [], None, "evening"
        )

        return {
            "type": "evening",
            "generated_at": now.isoformat(),
            "tomorrow_meetings": len(tomorrow_meetings),
            "completed_today": len(completed_reminders),
            "briefing": briefing_text,
            "details": {
                "tomorrow_calendar": tomorrow_meetings,
                "tomorrow_reminders": tomorrow_reminders,
                "completed_today": completed_reminders
            }
        }

    async def _get_todays_meetings(self) -> list[dict]:
        """Get meetings for today"""
        async with async_session() as session:
            now = datetime.now(timezone.utc)
            today_end = now.replace(hour=23, minute=59, second=59)

            result = await session.execute(
                select(Meeting).where(
                    Meeting.start_time >= now,
                    Meeting.start_time <= today_end
                ).order_by(Meeting.start_time)
            )
            meetings = result.scalars().all()

            return [
                {
                    "title": m.title,
                    "start": m.start_time.isoformat(),
                    "location": m.location,
                    "attendees": m.attendees
                }
                for m in meetings
            ]

    async def _get_meetings_between(self, start: datetime, end: datetime) -> list[dict]:
        """Get meetings in date range"""
        async with async_session() as session:
            result = await session.execute(
                select(Meeting).where(
                    Meeting.start_time >= start,
                    Meeting.start_time <= end
                ).order_by(Meeting.start_time)
            )
            meetings = result.scalars().all()

            return [
                {
                    "title": m.title,
                    "start": m.start_time.isoformat(),
                    "location": m.location
                }
                for m in meetings
            ]

    async def _get_todays_reminders(self) -> list[dict]:
        """Get reminders for today"""
        async with async_session() as session:
            now = datetime.now(timezone.utc)
            today_end = now.replace(hour=23, minute=59, second=59)

            result = await session.execute(
                select(Reminder).where(
                    Reminder.remind_at >= now,
                    Reminder.remind_at <= today_end,
                    Reminder.completed == False
                ).order_by(Reminder.remind_at)
            )
            reminders = result.scalars().all()

            return [
                {
                    "text": r.text,
                    "time": r.remind_at.isoformat()
                }
                for r in reminders
            ]

    async def _get_reminders_between(self, start: datetime, end: datetime) -> list[dict]:
        """Get reminders in date range"""
        async with async_session() as session:
            result = await session.execute(
                select(Reminder).where(
                    Reminder.remind_at >= start,
                    Reminder.remind_at <= end,
                    Reminder.completed == False
                ).order_by(Reminder.remind_at)
            )
            reminders = result.scalars().all()

            return [{"text": r.text, "time": r.remind_at.isoformat()} for r in reminders]

    async def _get_completed_reminders_today(self) -> list[dict]:
        """Get reminders completed today"""
        async with async_session() as session:
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0)

            result = await session.execute(
                select(Reminder).where(
                    Reminder.created_at >= today_start,
                    Reminder.completed == True
                )
            )
            reminders = result.scalars().all()

            return [{"text": r.text} for r in reminders]

    async def _get_recent_notes(self) -> list[dict]:
        """Get recent important notes"""
        async with async_session() as session:
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)

            result = await session.execute(
                select(Note).where(
                    Note.created_at >= yesterday
                ).order_by(Note.created_at.desc()).limit(5)
            )
            notes = result.scalars().all()

            return [{"content": n.content[:100]} for n in notes]

    async def _get_weather_summary(self) -> Optional[dict]:
        """Get weather summary - TODO: integrate weather API"""
        # TODO: Integrate with weather API
        return {"summary": "Weather data not available", "temp": None}

    async def _generate_briefing_text(
        self,
        calendar: list,
        reminders: list,
        notes: list,
        weather: Optional[dict],
        briefing_type: str
    ) -> str:
        """Generate natural language briefing using Claude"""

        claude = get_claude_llm()

        if briefing_type == "morning":
            prompt = f"""Generate a concise morning briefing in JARVIS style.

Today's Calendar ({len(calendar)} meetings):
{calendar}

Reminders ({len(reminders)} items):
{reminders}

Recent Notes:
{notes}

Weather: {weather}

Generate a brief, professional morning briefing (3-4 sentences max).
Address user as "sir" or "ma'am". Focus on priorities and prep needed."""

        else:  # evening
            prompt = f"""Generate a concise evening briefing in JARVIS style.

Tomorrow's Schedule ({len(calendar)} meetings):
{calendar}

Tomorrow's Reminders ({len(reminders)} items):
{reminders}

Generate a brief evening summary and tomorrow preview (3-4 sentences max).
Address user as "sir" or "ma'am". Focus on what to prepare for tomorrow."""

        try:
            response = await claude.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500
            )

            return response["message"]["content"]

        except Exception as e:
            logger.error(f"Failed to generate briefing: {e}")
            # Fallback to simple text
            if briefing_type == "morning":
                return f"Good morning. You have {len(calendar)} meetings and {len(reminders)} reminders today."
            else:
                return f"Good evening. Tomorrow you have {len(calendar)} meetings and {len(reminders)} reminders."


_briefing_service: Optional[BriefingService] = None


def get_briefing_service() -> BriefingService:
    """Get briefing service instance"""
    global _briefing_service
    if _briefing_service is None:
        _briefing_service = BriefingService()
    return _briefing_service
