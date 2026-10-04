"""Long-term Memory Service — per-user semantic memory."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import ConversationLog, LongTermMemory

logger = logging.getLogger(__name__)


class LongTermMemoryService:
    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def remember(
        self,
        content: str,
        memory_type: str = "conversation",
        context: Optional[str] = None,
        importance: float = 0.5,
    ) -> int:
        memory = LongTermMemory(
            user_id=self.user_id,
            content=content,
            memory_type=memory_type,
            context=context,
            importance=importance,
            access_count=0,
        )
        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        logger.info("Stored long-term memory: %s...", content[:50])
        return memory.id

    async def recall(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        stmt = select(LongTermMemory).where(
            LongTermMemory.user_id == self.user_id,
            or_(
                LongTermMemory.content.ilike(f"%{query}%"),
                LongTermMemory.context.ilike(f"%{query}%"),
            ),
        )
        if memory_type:
            stmt = stmt.where(LongTermMemory.memory_type == memory_type)
        stmt = stmt.order_by(
            LongTermMemory.importance.desc(),
            LongTermMemory.created_at.desc(),
        ).limit(limit)

        result = await self.db.execute(stmt)
        memories = result.scalars().all()

        now = datetime.now(timezone.utc)
        for m in memories:
            m.access_count += 1
            m.last_accessed = now
        await self.db.commit()

        return [
            {
                "id": m.id,
                "content": m.content,
                "type": m.memory_type,
                "context": m.context,
                "importance": m.importance,
                "created_at": m.created_at.isoformat(),
                "access_count": m.access_count,
            }
            for m in memories
        ]

    async def search_conversations(
        self,
        query: str,
        days_back: int = 30,
        limit: int = 10,
    ) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        stmt = (
            select(ConversationLog)
            .where(
                ConversationLog.user_id == self.user_id,
                ConversationLog.timestamp >= since,
                ConversationLog.content.ilike(f"%{query}%"),
            )
            .order_by(ConversationLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        logs = result.scalars().all()
        return [
            {
                "id": log.id,
                "role": log.role,
                "content": log.content,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in logs
        ]

    async def forget(self, memory_id: int) -> bool:
        result = await self.db.execute(
            select(LongTermMemory).where(
                LongTermMemory.id == memory_id,
                LongTermMemory.user_id == self.user_id,
            )
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return False
        await self.db.delete(memory)
        await self.db.commit()
        logger.info("Forgot memory %d", memory_id)
        return True

    async def get_memory_stats(self) -> dict:
        total = await self.db.scalar(
            select(func.count(LongTermMemory.id)).where(
                LongTermMemory.user_id == self.user_id
            )
        )
        by_type_rows = await self.db.execute(
            select(LongTermMemory.memory_type, func.count(LongTermMemory.id))
            .where(LongTermMemory.user_id == self.user_id)
            .group_by(LongTermMemory.memory_type)
        )
        type_counts = dict(by_type_rows.all())
        return {
            "total_memories": total or 0,
            "by_type": type_counts,
            "oldest": await self._get_oldest_memory(),
            "most_accessed": await self._get_most_accessed(),
        }

    async def _get_oldest_memory(self) -> Optional[dict]:
        result = await self.db.execute(
            select(LongTermMemory)
            .where(LongTermMemory.user_id == self.user_id)
            .order_by(LongTermMemory.created_at.asc())
            .limit(1)
        )
        memory = result.scalar_one_or_none()
        if memory:
            return {"content": memory.content[:100], "created_at": memory.created_at.isoformat()}
        return None

    async def _get_most_accessed(self) -> Optional[dict]:
        result = await self.db.execute(
            select(LongTermMemory)
            .where(
                LongTermMemory.user_id == self.user_id,
                LongTermMemory.access_count > 0,
            )
            .order_by(LongTermMemory.access_count.desc())
            .limit(1)
        )
        memory = result.scalar_one_or_none()
        if memory:
            return {"content": memory.content[:100], "access_count": memory.access_count}
        return None
