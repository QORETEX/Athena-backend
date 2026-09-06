"""
Long-term Memory Service - Semantic memory across all conversations
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, or_, func

from app.db import async_session, LongTermMemory, ConversationLog

logger = logging.getLogger(__name__)


class LongTermMemoryService:
    """
    Store and retrieve long-term semantic memories
    Enables JARVIS to remember conversations, facts, preferences
    """

    async def remember(
        self,
        content: str,
        memory_type: str = "conversation",
        context: Optional[str] = None,
        importance: float = 0.5
    ) -> int:
        """
        Store a memory

        Args:
            content: What to remember
            memory_type: conversation, fact, preference, event
            context: Additional context
            importance: 0.0 to 1.0

        Returns:
            Memory ID
        """
        async with async_session() as session:
            memory = LongTermMemory(
                content=content,
                memory_type=memory_type,
                context=context,
                importance=importance,
                access_count=0
            )

            session.add(memory)
            await session.commit()
            await session.refresh(memory)

            logger.info(f"Stored long-term memory: {content[:50]}...")
            return memory.id

    async def recall(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 5
    ) -> list[dict]:
        """
        Search memories

        Args:
            query: Search query
            memory_type: Filter by type
            limit: Max results

        Returns:
            List of matching memories
        """
        async with async_session() as session:
            # Simple keyword search (TODO: use embeddings for semantic search)
            stmt = select(LongTermMemory).where(
                or_(
                    LongTermMemory.content.ilike(f"%{query}%"),
                    LongTermMemory.context.ilike(f"%{query}%")
                )
            )

            if memory_type:
                stmt = stmt.where(LongTermMemory.memory_type == memory_type)

            stmt = stmt.order_by(
                LongTermMemory.importance.desc(),
                LongTermMemory.created_at.desc()
            ).limit(limit)

            result = await session.execute(stmt)
            memories = result.scalars().all()

            # Update access counts
            for memory in memories:
                memory.access_count += 1
                memory.last_accessed = datetime.now(timezone.utc)

            await session.commit()

            return [
                {
                    "id": m.id,
                    "content": m.content,
                    "type": m.memory_type,
                    "context": m.context,
                    "importance": m.importance,
                    "created_at": m.created_at.isoformat(),
                    "access_count": m.access_count
                }
                for m in memories
            ]

    async def search_conversations(
        self,
        query: str,
        days_back: int = 30,
        limit: int = 10
    ) -> list[dict]:
        """
        Search past conversations

        Enables: "What did I say about the Johnson project last week?"
        """
        async with async_session() as session:
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(days=days_back)

            stmt = select(ConversationLog).where(
                ConversationLog.timestamp >= since,
                ConversationLog.content.ilike(f"%{query}%")
            ).order_by(ConversationLog.timestamp.desc()).limit(limit)

            result = await session.execute(stmt)
            logs = result.scalars().all()

            return [
                {
                    "id": log.id,
                    "role": log.role,
                    "content": log.content,
                    "timestamp": log.timestamp.isoformat()
                }
                for log in logs
            ]

    async def get_recent_context(self, limit: int = 20) -> str:
        """
        Get recent conversation context for LLM

        Returns formatted string of recent interactions
        """
        async with async_session() as session:
            result = await session.execute(
                select(ConversationLog)
                .order_by(ConversationLog.timestamp.desc())
                .limit(limit)
            )
            logs = result.scalars().all()

            # Format as context
            context_parts = []
            for log in reversed(logs):  # Chronological order
                context_parts.append(f"{log.role}: {log.content[:200]}")

            return "\n".join(context_parts)

    async def forget(self, memory_id: int) -> bool:
        """Delete a memory"""
        async with async_session() as session:
            result = await session.execute(
                select(LongTermMemory).where(LongTermMemory.id == memory_id)
            )
            memory = result.scalar_one_or_none()

            if memory:
                await session.delete(memory)
                await session.commit()
                logger.info(f"Forgot memory {memory_id}")
                return True

            return False

    async def get_memory_stats(self) -> dict:
        """Get memory statistics"""
        async with async_session() as session:
            total = await session.execute(select(func.count(LongTermMemory.id)))
            total_count = total.scalar()

            by_type = await session.execute(
                select(
                    LongTermMemory.memory_type,
                    func.count(LongTermMemory.id)
                ).group_by(LongTermMemory.memory_type)
            )
            type_counts = dict(by_type.all())

            return {
                "total_memories": total_count,
                "by_type": type_counts,
                "oldest": await self._get_oldest_memory(),
                "most_accessed": await self._get_most_accessed()
            }

    async def _get_oldest_memory(self) -> Optional[dict]:
        """Get oldest stored memory"""
        async with async_session() as session:
            result = await session.execute(
                select(LongTermMemory).order_by(LongTermMemory.created_at.asc()).limit(1)
            )
            memory = result.scalar_one_or_none()

            if memory:
                return {
                    "content": memory.content[:100],
                    "created_at": memory.created_at.isoformat()
                }
            return None

    async def _get_most_accessed(self) -> Optional[dict]:
        """Get most frequently accessed memory"""
        async with async_session() as session:
            result = await session.execute(
                select(LongTermMemory)
                .where(LongTermMemory.access_count > 0)
                .order_by(LongTermMemory.access_count.desc())
                .limit(1)
            )
            memory = result.scalar_one_or_none()

            if memory:
                return {
                    "content": memory.content[:100],
                    "access_count": memory.access_count
                }
            return None


_longterm_memory_service: Optional[LongTermMemoryService] = None


def get_longterm_memory_service() -> LongTermMemoryService:
    """Get long-term memory service instance"""
    global _longterm_memory_service
    if _longterm_memory_service is None:
        _longterm_memory_service = LongTermMemoryService()
    return _longterm_memory_service
