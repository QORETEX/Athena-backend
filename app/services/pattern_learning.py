"""
Pattern Learning Service - Learn user behaviors and preferences
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.db import async_session, UserPattern

logger = logging.getLogger(__name__)


class PatternLearningService:
    """
    Learn and apply user behavior patterns

    Examples:
    - User usually leaves for work at 8:30 AM
    - User prefers coffee before meetings
    - User orders pizza on Friday nights
    - User sleeps at 10:30 PM
    """

    async def record_pattern(
        self,
        pattern_type: str,
        pattern_key: str,
        pattern_value: str,
        confidence: float = 0.5
    ) -> int:
        """
        Record or update a pattern

        Args:
            pattern_type: "time", "preference", "routine", "location"
            pattern_key: Specific pattern identifier
            pattern_value: Pattern data (can be JSON)
            confidence: 0.0 to 1.0

        Returns:
            Pattern ID
        """
        async with async_session() as session:
            # Check if pattern exists
            result = await session.execute(
                select(UserPattern).where(
                    UserPattern.pattern_type == pattern_type,
                    UserPattern.pattern_key == pattern_key
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing pattern
                existing.pattern_value = pattern_value
                existing.occurrences += 1
                existing.confidence = min(1.0, existing.confidence + 0.1)
                existing.last_seen = datetime.now(timezone.utc)
                pattern_id = existing.id

            else:
                # Create new pattern
                pattern = UserPattern(
                    pattern_type=pattern_type,
                    pattern_key=pattern_key,
                    pattern_value=pattern_value,
                    confidence=confidence,
                    occurrences=1
                )
                session.add(pattern)
                await session.flush()
                pattern_id = pattern.id

            await session.commit()
            logger.debug(f"Recorded pattern: {pattern_type}/{pattern_key}")
            return pattern_id

    async def get_pattern(
        self,
        pattern_type: str,
        pattern_key: str
    ) -> Optional[dict]:
        """Get a specific pattern"""
        async with async_session() as session:
            result = await session.execute(
                select(UserPattern).where(
                    UserPattern.pattern_type == pattern_type,
                    UserPattern.pattern_key == pattern_key
                )
            )
            pattern = result.scalar_one_or_none()

            if pattern:
                return {
                    "type": pattern.pattern_type,
                    "key": pattern.pattern_key,
                    "value": pattern.pattern_value,
                    "confidence": pattern.confidence,
                    "occurrences": pattern.occurrences,
                    "last_seen": pattern.last_seen.isoformat()
                }

            return None

    async def get_all_patterns(
        self,
        pattern_type: Optional[str] = None,
        min_confidence: float = 0.5
    ) -> list[dict]:
        """Get all learned patterns"""
        async with async_session() as session:
            stmt = select(UserPattern).where(
                UserPattern.confidence >= min_confidence
            )

            if pattern_type:
                stmt = stmt.where(UserPattern.pattern_type == pattern_type)

            stmt = stmt.order_by(UserPattern.confidence.desc())

            result = await session.execute(stmt)
            patterns = result.scalars().all()

            return [
                {
                    "type": p.pattern_type,
                    "key": p.pattern_key,
                    "value": p.pattern_value,
                    "confidence": p.confidence,
                    "occurrences": p.occurrences
                }
                for p in patterns
            ]

    async def detect_anomaly(
        self,
        pattern_type: str,
        pattern_key: str,
        current_value: str
    ) -> Optional[dict]:
        """
        Detect if current behavior deviates from pattern

        Returns anomaly details if detected
        """
        pattern = await self.get_pattern(pattern_type, pattern_key)

        if not pattern or pattern["confidence"] < 0.7:
            return None  # No strong pattern established

        # Compare current value with expected
        if pattern["value"] != current_value:
            return {
                "pattern_type": pattern_type,
                "pattern_key": pattern_key,
                "expected": pattern["value"],
                "actual": current_value,
                "confidence": pattern["confidence"],
                "message": f"Unusual: Expected {pattern['value']}, got {current_value}"
            }

        return None

    # Specific pattern helpers

    async def learn_wake_time(self, wake_time: str, day_of_week: Optional[str] = None):
        """Learn user's wake time"""
        key = f"wake_time_{day_of_week}" if day_of_week else "wake_time_general"
        await self.record_pattern("time", key, wake_time, confidence=0.6)

    async def learn_leave_time(self, leave_time: str, destination: str):
        """Learn when user leaves for specific destinations"""
        await self.record_pattern("time", f"leave_for_{destination}", leave_time, confidence=0.6)

    async def learn_preference(self, preference_key: str, preference_value: str):
        """Learn user preference"""
        await self.record_pattern("preference", preference_key, preference_value, confidence=0.7)

    async def learn_routine(self, routine_name: str, routine_time: str):
        """Learn routine timing"""
        await self.record_pattern("routine", routine_name, routine_time, confidence=0.6)

    async def get_expected_wake_time(self, day_of_week: str) -> Optional[str]:
        """Get expected wake time for day"""
        pattern = await self.get_pattern("time", f"wake_time_{day_of_week}")
        if pattern:
            return pattern["value"]

        # Fall back to general wake time
        pattern = await self.get_pattern("time", "wake_time_general")
        return pattern["value"] if pattern else None


_pattern_learning_service: Optional[PatternLearningService] = None


def get_pattern_learning_service() -> PatternLearningService:
    """Get pattern learning service instance"""
    global _pattern_learning_service
    if _pattern_learning_service is None:
        _pattern_learning_service = PatternLearningService()
    return _pattern_learning_service
