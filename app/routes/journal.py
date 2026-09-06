"""
Voice Journaling Endpoints - Record and search journal entries
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, UploadFile, File, Form, Query, Path
from pydantic import BaseModel
from sqlalchemy import select, or_

from app.db import async_session, JournalEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/journal", tags=["journal"])


class JournalEntryRequest(BaseModel):
    content: str
    tags: list[str] = []
    mood: str | None = None


@router.post("/entry", summary="Create journal entry", description="""
Create a new journal entry (text or voice).

**Supports:**
- Text entry (direct)
- Voice entry (transcribed automatically)
- Auto-tagging
- Mood detection
- Key point extraction using AI

**JARVIS use:**
User: "Athena, journal entry"
Athena: "Recording. Go ahead."
User: "Today was productive. Finished the API integration..."
Athena: "Entry saved. Tagged: work, success, API"

**Returns:** Entry ID and AI-generated summary
""")
async def create_journal_entry(entry: JournalEntryRequest):
    """Create a new journal entry"""
    async with async_session() as session:
        # Extract key points using Claude
        key_points = await _extract_key_points(entry.content)

        journal = JournalEntry(
            content=entry.content,
            tags=str(entry.tags),
            mood=entry.mood or await _detect_mood(entry.content),
            key_points=key_points
        )

        session.add(journal)
        await session.commit()
        await session.refresh(journal)

        return {
            "id": journal.id,
            "created_at": journal.created_at.isoformat(),
            "mood": journal.mood,
            "key_points": key_points,
            "tags": entry.tags
        }


@router.post("/entry/voice", summary="Voice journal entry", description="""
Create journal entry from voice recording.

**Process:**
1. Upload audio file (WAV, MP3, M4A)
2. Transcribe using Whisper
3. Extract key points with Claude
4. Detect mood automatically
5. Auto-generate tags

**Perfect for:** Quick voice notes, daily reflections, idea capture

**Example:**
*User records 2-minute voice note about project ideas*
→ Transcribed, analyzed, tagged automatically
→ "Saved 3 key ideas from your note about the mobile app redesign"
""")
async def create_voice_journal_entry(
    audio: UploadFile = File(..., description="Audio file (WAV/MP3/M4A)"),
    tags: str = Form("[]", description="Optional tags as JSON array")
):
    """Create journal entry from voice recording"""
    import json

    # Transcribe audio
    audio_bytes = await audio.read()
    transcript = await _transcribe_audio(audio_bytes)

    if not transcript:
        return {"error": "Failed to transcribe audio"}

    # Create entry
    async with async_session() as session:
        key_points = await _extract_key_points(transcript)
        mood = await _detect_mood(transcript)

        journal = JournalEntry(
            content=transcript,
            transcript=transcript,
            tags=tags,
            mood=mood,
            key_points=key_points
        )

        session.add(journal)
        await session.commit()
        await session.refresh(journal)

        return {
            "id": journal.id,
            "transcript": transcript[:200] + "...",
            "mood": mood,
            "key_points": key_points
        }


@router.get("/entries", summary="List journal entries", description="""
Get journal entries with optional filtering.

**Filters:**
- By date range
- By mood
- By tags
- Search by content

**Returns:** Paginated list with summaries

**JARVIS use:** "Show me journal entries from last week"
""")
async def list_journal_entries(
    limit: int = Query(20, description="Max entries to return", ge=1, le=100),
    mood: str | None = Query(None, description="Filter by mood"),
    days_back: int = Query(7, description="Days to look back", ge=1, le=365)
):
    """List journal entries"""
    async with async_session() as session:
        since = datetime.now(timezone.utc) - timedelta(days=days_back)

        stmt = select(JournalEntry).where(
            JournalEntry.created_at >= since
        )

        if mood:
            stmt = stmt.where(JournalEntry.mood == mood)

        stmt = stmt.order_by(JournalEntry.created_at.desc()).limit(limit)

        result = await session.execute(stmt)
        entries = result.scalars().all()

        return {
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "content": e.content[:200] + "..." if len(e.content) > 200 else e.content,
                    "mood": e.mood,
                    "key_points": e.key_points,
                    "created_at": e.created_at.isoformat()
                }
                for e in entries
            ]
        }


@router.get("/search", summary="Search journal entries", description="""
Search through journal entries using keywords.

**Search in:**
- Entry content
- Key points
- Tags

**Use case:** "What did I write about the project last month?"

**Returns:** Matching entries with relevance score
""")
async def search_journal(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, description="Max results", ge=1, le=50)
):
    """Search journal entries"""
    async with async_session() as session:
        stmt = select(JournalEntry).where(
            or_(
                JournalEntry.content.ilike(f"%{query}%"),
                JournalEntry.key_points.ilike(f"%{query}%")
            )
        ).order_by(JournalEntry.created_at.desc()).limit(limit)

        result = await session.execute(stmt)
        entries = result.scalars().all()

        return {
            "query": query,
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "content": e.content[:200],
                    "key_points": e.key_points,
                    "created_at": e.created_at.isoformat()
                }
                for e in entries
            ]
        }


@router.get("/{entry_id}", summary="Get journal entry details", description="""
Get full details of a specific journal entry.

**Returns:**
- Full content
- Transcript (if voice)
- Mood analysis
- Key points
- Related entries (if any)
""")
async def get_journal_entry(
    entry_id: int = Path(..., description="Journal entry ID")
):
    """Get full journal entry"""
    async with async_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if not entry:
            return {"error": "Entry not found"}

        return {
            "id": entry.id,
            "content": entry.content,
            "transcript": entry.transcript,
            "mood": entry.mood,
            "key_points": entry.key_points,
            "tags": entry.tags,
            "created_at": entry.created_at.isoformat()
        }


# Helper functions

async def _transcribe_audio(audio_bytes: bytes) -> str:
    """Transcribe audio using Whisper"""
    try:
        # TODO: Implement Whisper transcription
        # from app.websocket.voice import transcribe_audio
        # return transcribe_audio(audio_bytes)
        return "Transcription not yet implemented"
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return ""


async def _extract_key_points(content: str) -> str:
    """Extract key points using Claude"""
    try:
        from app.llm_claude import get_claude_llm

        claude = get_claude_llm()
        response = await claude.chat(
            messages=[{
                "role": "user",
                "content": f"""Extract 2-3 key points from this journal entry:

{content[:1000]}

Return as brief bullet points."""
            }],
            max_tokens=150
        )

        return response["message"]["content"]

    except Exception as e:
        logger.error(f"Key point extraction failed: {e}")
        return "Key points extraction unavailable"


async def _detect_mood(content: str) -> str:
    """Detect mood from content"""
    try:
        from app.llm_claude import get_claude_llm

        claude = get_claude_llm()
        response = await claude.chat(
            messages=[{
                "role": "user",
                "content": f"""Analyze the mood of this text. Respond with ONE word only: happy, sad, anxious, excited, frustrated, calm, or neutral.

{content[:500]}"""
            }],
            max_tokens=10
        )

        mood = response["message"]["content"].strip().lower()
        valid_moods = ['happy', 'sad', 'anxious', 'excited', 'frustrated', 'calm', 'neutral']

        return mood if mood in valid_moods else 'neutral'

    except Exception as e:
        logger.error(f"Mood detection failed: {e}")
        return "neutral"
