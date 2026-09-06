"""
Calendar Integration Endpoints - Google Calendar sync
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Path

from app.services.calendar_service import get_calendar_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.post("/sync", summary="Sync calendar from Google", description="""
Fetch upcoming meetings from Google Calendar.

**What it syncs:**
- Upcoming meetings (default: next 7 days)
- Meeting details (title, time, location, attendees)
- Stores in database for offline access

**Auto-categorization:**
- Detects meeting type
- Links to relevant notes
- Prepares briefing materials

**JARVIS use:** Automatic daily sync for briefings
""")
async def sync_calendar(
    days_ahead: int = Query(7, description="Days to sync ahead", ge=1, le=30)
):
    """Sync upcoming meetings from Google Calendar"""
    calendar_service = get_calendar_service()
    meetings = await calendar_service.sync_upcoming_meetings(days_ahead)
    return {
        "status": "ok",
        "synced": len(meetings),
        "meetings": meetings
    }


@router.get("/next", summary="Get next meeting", description="""
Get details of the next upcoming meeting.

**Returns:**
- Meeting title
- Start time
- Location
- Attendees
- Minutes until meeting starts

**JARVIS use:** "Sir, your next meeting is in 15 minutes - Team Standup in Conference Room B"
""")
async def get_next_meeting():
    """Get next upcoming meeting"""
    calendar_service = get_calendar_service()
    meeting = await calendar_service.get_next_meeting()

    if not meeting:
        return {"message": "No upcoming meetings"}

    return meeting


@router.get("/{meeting_id}/prep", summary="Generate meeting prep brief", description="""
AI-generated meeting preparation brief using Claude.

**What it includes:**
- Meeting objectives
- Key context
- Attendee information
- Action items to prepare
- Past discussion points (if available)

**Example output:**
"Meeting with John Smith regarding Q4 targets. Last discussed: API integration concerns.
Prepare: updated metrics dashboard, timeline adjustments. John prefers data-driven presentations."
""")
async def get_meeting_prep(
    meeting_id: int = Path(..., description="Meeting ID from database")
):
    """Get AI-generated meeting preparation brief"""
    calendar_service = get_calendar_service()
    brief = await calendar_service.prepare_meeting_brief(meeting_id)
    return {
        "meeting_id": meeting_id,
        "prep_brief": brief
    }


@router.post("/initialize", summary="Initialize Google Calendar", description="""
Set up Google Calendar API connection (one-time setup).

**Setup steps:**
1. Enable Google Calendar API
2. Use same credentials as Gmail
3. Call this endpoint
4. Follow OAuth flow

**Required once per deployment**
""")
async def initialize_calendar():
    """Initialize Google Calendar API connection"""
    calendar_service = get_calendar_service()
    success = await calendar_service.initialize()
    return {
        "status": "ok" if success else "error",
        "message": "Calendar API initialized" if success else "Failed to initialize. Check credentials."
    }
