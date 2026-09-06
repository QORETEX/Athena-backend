from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Reminder, get_db
from app.schemas import ReminderResponse

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class ReminderCreate(BaseModel):
    text: str
    remind_at: datetime


class ReminderUpdate(BaseModel):
    text: str | None = None
    remind_at: datetime | None = None
    completed: bool | None = None


@router.get("/", response_model=list[ReminderResponse])
async def list_reminders(
    completed: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Reminder).order_by(Reminder.remind_at)
    if completed is not None:
        stmt = stmt.where(Reminder.completed == completed)
    result = await db.execute(stmt)
    reminders = result.scalars().all()
    return [
        ReminderResponse(
            id=r.id,
            text=r.text,
            remind_at=r.remind_at,
            completed=r.completed,
            created_at=r.created_at,
        )
        for r in reminders
    ]


@router.post("/", response_model=ReminderResponse, status_code=201)
async def create_reminder(body: ReminderCreate, db: AsyncSession = Depends(get_db)):
    reminder = Reminder(text=body.text, remind_at=body.remind_at)
    db.add(reminder)
    await db.flush()
    await db.refresh(reminder)

    try:
        from app.scheduler import schedule_reminder

        schedule_reminder(reminder.id, reminder.remind_at, reminder.text)
    except Exception:
        pass

    return ReminderResponse(
        id=reminder.id,
        text=reminder.text,
        remind_at=reminder.remind_at,
        completed=reminder.completed,
        created_at=reminder.created_at,
    )


@router.patch("/{reminder_id}", response_model=ReminderResponse)
async def update_reminder(
    reminder_id: int,
    body: ReminderUpdate,
    db: AsyncSession = Depends(get_db),
):
    reminder = await db.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if body.text is not None:
        reminder.text = body.text
    if body.remind_at is not None:
        reminder.remind_at = body.remind_at
    if body.completed is not None:
        reminder.completed = body.completed

    await db.flush()
    await db.refresh(reminder)

    return ReminderResponse(
        id=reminder.id,
        text=reminder.text,
        remind_at=reminder.remind_at,
        completed=reminder.completed,
        created_at=reminder.created_at,
    )


@router.delete("/{reminder_id}", status_code=204)
async def delete_reminder(
    reminder_id: int,
    db: AsyncSession = Depends(get_db),
):
    reminder = await db.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await db.delete(reminder)
