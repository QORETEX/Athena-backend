from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import Note, async_session
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)


async def handle_save_note(content: str, tags: list[str] | None = None) -> dict:
    note = Note(
        content=content,
        tags=json.dumps(tags or []),
    )
    async with async_session() as session:
        session.add(note)
        await session.commit()
        await session.refresh(note)

    return {"success": True, "note_id": note.id}


async def handle_search_notes(query: str) -> dict:
    async with async_session() as session:
        result = await session.execute(
            select(Note)
            .where(Note.content.ilike(f"%{query}%"))
            .order_by(Note.created_at.desc())
            .limit(10)
        )
        notes = result.scalars().all()

    return {
        "notes": [
            {
                "id": n.id,
                "content": n.content,
                "tags": json.loads(n.tags) if n.tags else [],
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ]
    }


async def handle_delete_note(note_id: int) -> dict:
    async with async_session() as session:
        result = await session.execute(select(Note).where(Note.id == note_id))
        note = result.scalar_one_or_none()
        if not note:
            return {"success": False, "error": f"Note {note_id} not found"}
        await session.delete(note)
        await session.commit()

    return {"success": True, "note_id": note_id}


register_skill(
    Skill(
        name="save_note",
        description="Save a note for the user. Use this when the user asks to remember something, take a note, or jot something down.",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The note content",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorization",
                },
            },
            "required": ["content"],
        },
        handler=handle_save_note,
    )
)

register_skill(
    Skill(
        name="search_notes",
        description="Search the user's saved notes by keyword.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term to find in notes",
                },
            },
            "required": ["query"],
        },
        handler=handle_search_notes,
    )
)

register_skill(
    Skill(
        name="delete_note",
        description="Delete a specific note by its ID.",
        parameters={
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "integer",
                    "description": "The ID of the note to delete",
                },
            },
            "required": ["note_id"],
        },
        handler=handle_delete_note,
    )
)
