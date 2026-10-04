"""Pattern Learning Service — per-user behavior patterns."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import UserPattern

logger = logging.getLogger(__name__)


class PatternLearningService:
    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def record_pattern(
        self,
        pattern_type: str,
        pattern_key: str,
        pattern_value: str,
        confidence: float = 0.5,
    ) -> int:
        result = await self.db.execute(
            select(UserPattern).where(
                UserPattern.user_id == self.user_id,
                UserPattern.pattern_type == pattern_type,
                UserPattern.pattern_key == pattern_key,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.pattern_value = pattern_value
            existing.occurrences += 1
            existing.confidence = min(1.0, existing.confidence + 0.1)
            existing.last_seen = datetime.now(timezone.utc)
            pattern_id = existing.id
        else:
            pattern = UserPattern(
                user_id=self.user_id,
                pattern_type=pattern_type,
                pattern_key=pattern_key,
                pattern_value=pattern_value,
                confidence=confidence,
                occurrences=1,
            )
            self.db.add(pattern)
            await self.db.flush()
            pattern_id = pattern.id

        await self.db.commit()
        logger.debug("Recorded pattern: %s/%s", pattern_type, pattern_key)
        return pattern_id

    async def get_pattern(self, pattern_type: str, pattern_key: str) -> Optional[dict]:
        result = await self.db.execute(
            select(UserPattern).where(
                UserPattern.user_id == self.user_id,
                UserPattern.pattern_type == pattern_type,
                UserPattern.pattern_key == pattern_key,
            )
        )
        pattern = result.scalar_one_or_none()
        if not pattern:
            return None
        return {
            "type": pattern.pattern_type,
            "key": pattern.pattern_key,
            "value": pattern.pattern_value,
            "confidence": pattern.confidence,
            "occurrences": pattern.occurrences,
            "last_seen": pattern.last_seen.isoformat(),
        }

    async def get_all_patterns(
        self,
        pattern_type: Optional[str] = None,
        min_confidence: float = 0.5,
    ) -> list[dict]:
        stmt = select(UserPattern).where(
            UserPattern.user_id == self.user_id,
            UserPattern.confidence >= min_confidence,
        )
        if pattern_type:
            stmt = stmt.where(UserPattern.pattern_type == pattern_type)
        stmt = stmt.order_by(UserPattern.confidence.desc())

        result = await self.db.execute(stmt)
        patterns = result.scalars().all()
        return [
            {
                "type": p.pattern_type,
                "key": p.pattern_key,
                "value": p.pattern_value,
                "confidence": p.confidence,
                "occurrences": p.occurrences,
            }
            for p in patterns
        ]

    async def detect_anomaly(
        self,
        pattern_type: str,
        pattern_key: str,
        current_value: str,
    ) -> Optional[dict]:
        pattern = await self.get_pattern(pattern_type, pattern_key)
        if not pattern or pattern["confidence"] < 0.7:
            return None
        if pattern["value"] != current_value:
            return {
                "pattern_type": pattern_type,
                "pattern_key": pattern_key,
                "expected": pattern["value"],
                "actual": current_value,
                "confidence": pattern["confidence"],
                "message": f"Unusual: Expected {pattern['value']}, got {current_value}",
            }
        return None
