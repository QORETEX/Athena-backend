"""
Focus Mode Intelligence Service
Detect and manage deep work sessions
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import FocusSession

logger = logging.getLogger(__name__)


class FocusService:
    """Service for managing focus mode and deep work sessions"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_focus_session(
        self,
        focus_type: str = "deep_work",
        planned_duration_minutes: Optional[int] = None,
        activity: Optional[str] = None,
        auto_detected: bool = False,
    ) -> FocusSession:
        """Start a new focus session"""
        session = FocusSession(
            start_time=datetime.now(timezone.utc),
            focus_type=focus_type,
            planned_duration_minutes=planned_duration_minutes,
            activity=activity,
            auto_detected=auto_detected,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        logger.info(f"Started {focus_type} session (auto: {auto_detected})")

        # Enable focus mode actions
        await self._enable_focus_mode(session)

        return session

    async def end_focus_session(
        self,
        session_id: int,
        notes: Optional[str] = None,
        productivity_score: Optional[float] = None,
    ) -> Optional[FocusSession]:
        """End an active focus session"""
        session = await self.get_session(session_id)
        if not session or session.end_time:
            return None

        session.end_time = datetime.now(timezone.utc)
        session.notes = notes
        session.productivity_score = productivity_score

        # Calculate actual duration
        duration = (session.end_time - session.start_time).total_seconds() / 60
        session.actual_duration_minutes = int(duration)

        await self.db.commit()
        await self.db.refresh(session)

        logger.info(f"Ended focus session {session_id} - {duration:.0f} minutes")

        # Disable focus mode actions
        await self._disable_focus_mode(session)

        return session

    async def get_current_session(self) -> Optional[FocusSession]:
        """Get the currently active focus session"""
        result = await self.db.execute(
            select(FocusSession)
            .where(FocusSession.end_time.is_(None))
            .order_by(desc(FocusSession.start_time))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_session(self, session_id: int) -> Optional[FocusSession]:
        """Get a specific focus session"""
        result = await self.db.execute(
            select(FocusSession).where(FocusSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_recent_sessions(
        self, days: int = 7, limit: int = 20
    ) -> List[FocusSession]:
        """Get recent focus sessions"""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(FocusSession)
            .where(FocusSession.start_time >= start_date)
            .order_by(desc(FocusSession.start_time))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def increment_notifications_held(self, session_id: int) -> bool:
        """Increment count of notifications held during focus"""
        session = await self.get_session(session_id)
        if not session:
            return False

        session.notifications_held += 1
        await self.db.commit()
        return True

    async def increment_interruptions(self, session_id: int) -> bool:
        """Increment count of interruptions during focus"""
        session = await self.get_session(session_id)
        if not session:
            return False

        session.interruptions += 1
        await self.db.commit()
        return True

    async def detect_focus_session(self, context: Dict) -> Optional[FocusSession]:
        """
        Auto-detect focus session from user behavior
        Called by JARVIS brain

        Indicators:
        - No app switches for 30+ minutes
        - Specific productivity apps in use
        - Calendar has "focus" or "deep work" block
        """
        # Check if already in focus mode
        current = await self.get_current_session()
        if current:
            return current

        # Analyze context for focus indicators
        app_usage = context.get("app_usage", {})
        calendar = context.get("calendar", [])
        last_interaction = context.get("last_interaction_minutes_ago", 0)

        focus_detected = False
        focus_type = "deep_work"
        activity = None

        # Check calendar for focus blocks
        for event in calendar:
            title = event.get("title", "").lower()
            if any(
                keyword in title
                for keyword in ["focus", "deep work", "coding", "writing", "designing"]
            ):
                focus_detected = True
                activity = event.get("title")
                break

        # Check app usage patterns (30+ min in productivity apps)
        if not focus_detected:
            productivity_apps = [
                "vscode",
                "xcode",
                "pycharm",
                "sublime",
                "figma",
                "photoshop",
            ]
            for app_name in productivity_apps:
                if app_name in app_usage:
                    duration = app_usage[app_name].get("duration_minutes", 0)
                    if duration >= 30:
                        focus_detected = True
                        activity = f"Working in {app_name}"
                        break

        # Check for lack of interruptions (no interaction for 30+ min)
        if not focus_detected and last_interaction >= 30:
            focus_detected = True

        if focus_detected:
            logger.info(f"Auto-detected focus session: {activity}")
            return await self.start_focus_session(
                focus_type=focus_type,
                activity=activity,
                auto_detected=True,
            )

        return None

    async def _enable_focus_mode(self, session: FocusSession):
        """Enable focus mode protections"""
        # This would integrate with notification system
        logger.info("Focus mode enabled - holding non-urgent notifications")
        # TODO: Set user preference to hold notifications
        # await self.db.execute(...)

    async def _disable_focus_mode(self, session: FocusSession):
        """Disable focus mode protections"""
        logger.info(
            f"Focus mode disabled - {session.notifications_held} notifications held"
        )

        # Send notification about held items
        if session.notifications_held > 0:
            try:
                from app.notifications.push_service import get_push_service

                push_service = get_push_service()
                await push_service.send_push_notification(
                    title="Focus Session Complete",
                    body=f"You have {session.notifications_held} held notifications. Review now?",
                    data={"session_id": session.id},
                )
            except Exception as e:
                logger.error(f"Failed to send focus completion notification: {e}")

    async def get_focus_stats(self, days: int = 7) -> Dict:
        """Get focus session statistics"""
        sessions = await self.get_recent_sessions(days=days, limit=100)

        stats = {
            "total_sessions": len(sessions),
            "total_minutes": 0,
            "average_duration": 0.0,
            "longest_session": 0,
            "by_type": {},
            "auto_detected": 0,
            "manual": 0,
            "average_productivity": 0.0,
            "total_notifications_held": 0,
            "total_interruptions": 0,
            "sessions": [],
        }

        if not sessions:
            return stats

        total_duration = 0
        productivity_scores = []

        for session in sessions:
            duration = session.actual_duration_minutes or 0
            total_duration += duration

            if duration > stats["longest_session"]:
                stats["longest_session"] = duration

            # Count by type
            focus_type = session.focus_type
            stats["by_type"][focus_type] = stats["by_type"].get(focus_type, 0) + 1

            # Auto vs manual
            if session.auto_detected:
                stats["auto_detected"] += 1
            else:
                stats["manual"] += 1

            # Productivity scores
            if session.productivity_score:
                productivity_scores.append(session.productivity_score)

            # Notifications and interruptions
            stats["total_notifications_held"] += session.notifications_held
            stats["total_interruptions"] += session.interruptions

            # Add to sessions list
            stats["sessions"].append(
                {
                    "id": session.id,
                    "start_time": session.start_time.isoformat(),
                    "duration_minutes": duration,
                    "type": session.focus_type,
                    "activity": session.activity,
                    "productivity_score": session.productivity_score,
                }
            )

        stats["total_minutes"] = total_duration
        stats["average_duration"] = (
            round(total_duration / len(sessions), 1) if sessions else 0.0
        )
        stats["average_productivity"] = (
            round(sum(productivity_scores) / len(productivity_scores), 2)
            if productivity_scores
            else 0.0
        )

        return stats

    async def get_optimal_focus_times(self) -> List[Dict]:
        """
        Analyze past focus sessions to determine optimal focus times
        Returns recommended time blocks based on historical productivity
        """
        sessions = await self.get_recent_sessions(days=30, limit=200)

        # Group by hour of day and day of week
        time_blocks = {}  # {(day_of_week, hour): [session, ...]}

        for session in sessions:
            if not session.productivity_score:
                continue

            day = session.start_time.weekday()  # 0=Monday, 6=Sunday
            hour = session.start_time.hour

            key = (day, hour)
            if key not in time_blocks:
                time_blocks[key] = []

            time_blocks[key].append(session)

        # Calculate average productivity for each time block
        recommendations = []
        for (day, hour), block_sessions in time_blocks.items():
            avg_productivity = sum(s.productivity_score for s in block_sessions) / len(
                block_sessions
            )
            avg_duration = sum(
                s.actual_duration_minutes or 0 for s in block_sessions
            ) / len(block_sessions)

            if avg_productivity >= 7.0:  # High productivity threshold
                day_names = [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ]
                recommendations.append(
                    {
                        "day": day_names[day],
                        "hour": hour,
                        "time_display": f"{hour:02d}:00",
                        "average_productivity": round(avg_productivity, 2),
                        "average_duration_minutes": round(avg_duration, 0),
                        "session_count": len(block_sessions),
                    }
                )

        # Sort by productivity
        recommendations.sort(key=lambda x: x["average_productivity"], reverse=True)

        return recommendations[:10]  # Top 10 time blocks
