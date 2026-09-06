from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import ConversationLog, get_db
from app.schemas import ConversationLogResponse

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/", response_model=list[ConversationLogResponse])
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List conversation log entries, most recent first."""
    stmt = select(ConversationLog).order_by(ConversationLog.timestamp.desc())
    if role:
        stmt = stmt.where(ConversationLog.role == role)
    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        ConversationLogResponse(
            id=log.id,
            timestamp=log.timestamp,
            role=log.role,
            content=log.content,
            tool_calls=log.tool_calls,
        )
        for log in logs
    ]


@router.get("/stats")
async def conversation_stats(db: AsyncSession = Depends(get_db)):
    """Get conversation statistics."""
    total = await db.scalar(select(func.count(ConversationLog.id)))
    user_msgs = await db.scalar(
        select(func.count(ConversationLog.id)).where(ConversationLog.role == "user")
    )
    assistant_msgs = await db.scalar(
        select(func.count(ConversationLog.id)).where(ConversationLog.role == "assistant")
    )
    return {
        "total_messages": total or 0,
        "user_messages": user_msgs or 0,
        "assistant_messages": assistant_msgs or 0,
    }


@router.delete("/", status_code=204)
async def clear_conversations(db: AsyncSession = Depends(get_db)):
    """Clear all conversation logs."""
    from sqlalchemy import delete

    await db.execute(delete(ConversationLog))
