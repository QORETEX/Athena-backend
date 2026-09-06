from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Note, get_db
from app.schemas import NoteResponse

router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteCreate(BaseModel):
    content: str
    tags: list[str] = []


class NoteUpdate(BaseModel):
    content: str | None = None
    tags: list[str] | None = None


def _to_response(note: Note) -> NoteResponse:
    try:
        tags = json.loads(note.tags) if note.tags else []
    except (json.JSONDecodeError, TypeError):
        tags = []
    return NoteResponse(
        id=note.id,
        content=note.content,
        created_at=note.created_at,
        updated_at=note.updated_at,
        tags=tags,
    )


@router.get("/", response_model=list[NoteResponse])
async def list_notes(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Note).order_by(Note.created_at.desc())
    if search:
        stmt = stmt.where(Note.content.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    return [_to_response(n) for n in result.scalars().all()]


@router.post("/", response_model=NoteResponse, status_code=201)
async def create_note(body: NoteCreate, db: AsyncSession = Depends(get_db)):
    note = Note(content=body.content, tags=json.dumps(body.tags))
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return _to_response(note)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    body: NoteUpdate,
    db: AsyncSession = Depends(get_db),
):
    note = await db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if body.content is not None:
        note.content = body.content
    if body.tags is not None:
        note.tags = json.dumps(body.tags)
    note.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(note)
    return _to_response(note)


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db)):
    note = await db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
