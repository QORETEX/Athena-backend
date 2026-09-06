"""
Focus Mode Intelligence Routes
Manage deep work sessions and focus time
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.focus_service import FocusService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/focus", tags=["focus"])


class FocusSessionStart(BaseModel):
    focus_type: str = "deep_work"  # deep_work, meeting, creative, study
    planned_duration_minutes: Optional[int] = None
    activity: Optional[str] = None


class FocusSessionEnd(BaseModel):
    notes: Optional[str] = None
    productivity_score: Optional[float] = None  # 0-10


@router.post("/start", summary="Start focus session", description="""
Start a focus mode session.

**Focus types:**
- `deep_work` - Coding, writing, analysis
- `meeting` - In meeting/presentation
- `creative` - Design, brainstorming
- `study` - Learning, reading

**Example:**
```json
{
  "focus_type": "deep_work",
  "planned_duration_minutes": 90,
  "activity": "Implementing new feature"
}
```

**What happens:**
1. Non-urgent notifications are held
2. Interruption tracking begins
3. Calendar marked as busy (optional)
4. Phone goes to DND mode

**JARVIS use:**
User: "Athena, focus mode for 2 hours"
JARVIS: "Focus mode activated. Holding all non-urgent notifications. I'll alert you in 2 hours."

**User scenario:**
Deep work protection - no distractions for focused time.
""")
async def start_focus_session(
    session: FocusSessionStart, db: AsyncSession = Depends(get_db)
):
    """Start a focus session"""
    service = FocusService(db)

    started = await service.start_focus_session(
        focus_type=session.focus_type,
        planned_duration_minutes=session.planned_duration_minutes,
        activity=session.activity,
        auto_detected=False,
    )

    return {
        "session_id": started.id,
        "focus_type": started.focus_type,
        "start_time": started.start_time.isoformat(),
        "planned_duration": started.planned_duration_minutes,
        "status": "active",
        "message": "Focus mode activated",
    }


@router.post("/{session_id}/end", summary="End focus session", description="""
End an active focus session.

**Optional:**
- Notes about the session
- Productivity score (0-10)

**Example:**
```json
{
  "notes": "Completed feature implementation",
  "productivity_score": 8.5
}
```

**JARVIS response:**
"Focus session complete: 87 minutes. 5 notifications were held. Would you like to review them now?"

**Use case:** Track productivity and deep work effectiveness
""")
async def end_focus_session(
    session_id: int, end_data: FocusSessionEnd, db: AsyncSession = Depends(get_db)
):
    """End a focus session"""
    service = FocusService(db)

    ended = await service.end_focus_session(
        session_id=session_id,
        notes=end_data.notes,
        productivity_score=end_data.productivity_score,
    )

    if not ended:
        raise HTTPException(
            status_code=404, detail="Session not found or already ended"
        )

    return {
        "session_id": ended.id,
        "duration_minutes": ended.actual_duration_minutes,
        "notifications_held": ended.notifications_held,
        "interruptions": ended.interruptions,
        "productivity_score": ended.productivity_score,
        "message": "Focus session completed",
    }


@router.get("/current", summary="Get current focus session", description="""
Check if currently in focus mode.

**Returns:** Active session details or null if not in focus mode

**JARVIS use:** Check before showing notifications
"User is in deep work session, hold non-urgent notifications"
""")
async def get_current_session(db: AsyncSession = Depends(get_db)):
    """Get current active focus session"""
    service = FocusService(db)
    current = await service.get_current_session()

    if not current:
        return {"in_focus_mode": False, "session": None}

    # Calculate elapsed time
    from datetime import datetime, timezone

    elapsed = (datetime.now(timezone.utc) - current.start_time).total_seconds() / 60

    return {
        "in_focus_mode": True,
        "session": {
            "id": current.id,
            "focus_type": current.focus_type,
            "activity": current.activity,
            "start_time": current.start_time.isoformat(),
            "planned_duration": current.planned_duration_minutes,
            "elapsed_minutes": int(elapsed),
            "notifications_held": current.notifications_held,
            "auto_detected": current.auto_detected,
        },
    }


@router.get("/sessions", summary="Get focus session history", description="""
Get recent focus sessions.

**Query parameters:**
- `days` - Look back period (default: 7)
- `limit` - Max sessions to return (default: 20)

**Returns:** Recent focus sessions with productivity data

**Use case:** Analyze focus patterns and productivity trends
""")
async def get_sessions(
    days: int = Query(7, description="Days to look back"),
    limit: int = Query(20, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """Get recent focus sessions"""
    service = FocusService(db)
    sessions = await service.get_recent_sessions(days=days, limit=limit)

    return {
        "days": days,
        "count": len(sessions),
        "sessions": [
            {
                "id": s.id,
                "focus_type": s.focus_type,
                "activity": s.activity,
                "start_time": s.start_time.isoformat(),
                "duration_minutes": s.actual_duration_minutes,
                "notifications_held": s.notifications_held,
                "interruptions": s.interruptions,
                "productivity_score": s.productivity_score,
                "auto_detected": s.auto_detected,
            }
            for s in sessions
        ],
    }


@router.get("/stats", summary="Get focus statistics", description="""
Get focus session analytics.

**Query parameters:**
- `days` - Analysis period (default: 7)

**Returns:**
- Total focus time
- Average session duration
- Longest session
- Productivity trends
- Sessions by type
- Auto-detected vs manual sessions
- Total notifications held
- Total interruptions

**JARVIS insight:**
"Sir, your focus stats for this week:
 - 8 deep work sessions
 - Total: 12.5 hours focused
 - Average productivity: 7.8/10
 - 23 notifications held during focus time
 - Best time: Tuesday mornings (avg 8.5/10 productivity)"

**Use case:** Optimize deep work schedule
""")
async def get_focus_stats(
    days: int = Query(7, description="Days to analyze"),
    db: AsyncSession = Depends(get_db),
):
    """Get focus statistics"""
    service = FocusService(db)
    stats = await service.get_focus_stats(days=days)

    return stats


@router.get("/optimal-times", summary="Get optimal focus times", description="""
AI-powered analysis of your best focus times.

**Analyzes:**
- Historical productivity scores
- Time of day patterns
- Day of week patterns
- Average session durations

**Returns:** Top 10 time blocks for deep work

**JARVIS recommendation:**
"Sir, based on your productivity history:
 - Tuesday 9-11 AM: Average 8.7/10 productivity
 - Thursday 2-4 PM: Average 8.3/10 productivity
 - Wednesday 10 AM-12 PM: Average 8.1/10 productivity

Should I schedule your deep work during these times?"

**Use case:** Optimize calendar for maximum productivity
""")
async def get_optimal_times(db: AsyncSession = Depends(get_db)):
    """Get optimal focus times based on history"""
    service = FocusService(db)
    optimal_times = await service.get_optimal_focus_times()

    return {
        "recommendations": optimal_times,
        "message": "Best times for deep work based on your productivity history",
    }


@router.post("/detect", summary="Auto-detect focus session", description="""
Auto-detect if user is in focus mode based on context.

**Input context:**
- App usage (which apps, duration)
- Calendar events (focus blocks, meetings)
- Interaction patterns (no interruptions)
- Activity type

**Example:**
```json
{
  "context": {
    "app_usage": {
      "vscode": {"duration_minutes": 45}
    },
    "calendar": [
      {"title": "Deep Work Block", "start": "..."}
    ],
    "last_interaction_minutes_ago": 45
  }
}
```

**Returns:** Auto-started focus session if detected

**JARVIS proactive:**
"Sir, I noticed you've been coding for 45 minutes without interruption.
 I've enabled focus mode to protect your flow state.
 Holding all non-urgent notifications."

**Use case:** Automatic deep work protection without manual activation
""")
async def detect_focus(
    context: Dict = Body(..., description="Current user context"),
    db: AsyncSession = Depends(get_db),
):
    """Auto-detect and start focus session"""
    service = FocusService(db)
    session = await service.detect_focus_session(context)

    if session:
        return {
            "detected": True,
            "session_id": session.id,
            "focus_type": session.focus_type,
            "activity": session.activity,
            "message": "Focus mode auto-detected and activated",
        }
    else:
        return {"detected": False, "message": "No focus session detected"}


@router.post("/{session_id}/notification-held", summary="Record held notification", description="""
Increment count of notifications held during focus.

**JARVIS use:** Internal tracking - called when notification is held during focus mode
""")
async def record_held_notification(
    session_id: int, db: AsyncSession = Depends(get_db)
):
    """Record that a notification was held during focus"""
    service = FocusService(db)
    success = await service.increment_notifications_held(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"status": "recorded"}


@router.post("/{session_id}/interruption", summary="Record interruption", description="""
Increment count of interruptions during focus.

**JARVIS use:** Track when focus is broken (phone call, urgent alert, etc.)
""")
async def record_interruption(session_id: int, db: AsyncSession = Depends(get_db)):
    """Record an interruption during focus"""
    service = FocusService(db)
    success = await service.increment_interruptions(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"status": "recorded"}
