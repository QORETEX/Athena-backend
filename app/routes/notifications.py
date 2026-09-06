from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import NotificationLog, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ── Response models ───────────────────────────────────────


class NotificationResponse(BaseModel):
    id: int
    event_type: str
    priority: str
    title: str
    body: Optional[str] = None
    data: Optional[dict] = None
    read: bool = False
    created_at: str

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────


@router.get("/", response_model=list[NotificationResponse])
async def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List recent notifications, newest first."""
    stmt = (
        select(NotificationLog)
        .order_by(NotificationLog.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(NotificationLog.read == False)  # noqa: E712

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        NotificationResponse(
            id=n.id,
            event_type=n.event_type,
            priority=n.priority,
            title=n.title,
            body=n.body,
            data=json.loads(n.data) if n.data else None,
            read=n.read,
            created_at=n.created_at.isoformat() if n.created_at else "",
        )
        for n in rows
    ]


@router.post("/{notification_id}/read")
async def mark_read(notification_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a single notification as read."""
    notif = await db.get(NotificationLog, notification_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.read = True
    await db.flush()
    return {"id": notification_id, "read": True}


@router.post("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db)):
    """Mark all unread notifications as read."""
    stmt = (
        update(NotificationLog)
        .where(NotificationLog.read == False)  # noqa: E712
        .values(read=True)
    )
    result = await db.execute(stmt)
    return {"marked_read": result.rowcount}


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db)):
    """Return the count of unread notifications."""
    stmt = select(func.count(NotificationLog.id)).where(
        NotificationLog.read == False  # noqa: E712
    )
    result = await db.execute(stmt)
    count = result.scalar() or 0
    return {"count": count}
