"""
Quick Actions / Shortcuts Routes
Execute multi-step actions with single commands
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.quick_actions_service import QuickActionsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shortcuts", tags=["shortcuts"])


class QuickActionCreate(BaseModel):
    name: str
    trigger_phrase: str
    description: Optional[str] = None
    actions: List[Dict[str, Any]]
    category: str = "custom"


class QuickActionUpdate(BaseModel):
    name: Optional[str] = None
    trigger_phrase: Optional[str] = None
    description: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None
    enabled: Optional[bool] = None


@router.post("/actions", summary="Create quick action", description="""
Create a custom quick action shortcut.

**Example:**
```json
{
  "name": "heading_to_office",
  "trigger_phrase": "heading to office",
  "description": "Prepare for commute to office",
  "actions": [
    {"type": "check_calendar", "params": {}},
    {"type": "send_notification", "params": {"title": "Office Commute", "body": "Have a great day!"}},
    {"type": "log", "params": {"message": "User heading to office"}}
  ],
  "category": "custom"
}
```

**Action types:**
- `send_notification` - Push notification
- `create_reminder` - Timed reminder
- `start_focus_mode` - Enter focus mode
- `get_briefing` - Generate briefing
- `check_emails` - Check urgent emails
- `check_calendar` - Check next meeting
- `log` - Log message

**JARVIS use:**
User: "Athena, heading to office"
JARVIS executes: Check calendar → Check traffic → Start navigation → Play podcast

**Use case:** Multi-step workflows in one command
""")
async def create_action(
    action: QuickActionCreate, db: AsyncSession = Depends(get_db)
):
    """Create a quick action"""
    service = QuickActionsService(db)

    created = await service.create_action(
        name=action.name,
        trigger_phrase=action.trigger_phrase,
        actions=action.actions,
        description=action.description,
        category=action.category,
    )

    return {
        "id": created.id,
        "name": created.name,
        "trigger_phrase": created.trigger_phrase,
        "description": created.description,
        "category": created.category,
        "enabled": created.enabled,
    }


@router.get("/actions", summary="List quick actions", description="""
Get all quick actions.

**Query parameters:**
- `enabled_only` - Only enabled actions
- `category` - Filter by category (preset, custom, suggested)

**Returns:** All available quick actions

**Preset actions:**
- `morning` - Morning routine (briefing, emails, calendar)
- `focus` - Start deep work
- `wind_down` - Evening summary
- `catch_up` - Quick updates

**JARVIS use:** Display available shortcuts to user
""")
async def list_actions(
    enabled_only: bool = False,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all quick actions"""
    service = QuickActionsService(db)
    actions = await service.get_all_actions(
        enabled_only=enabled_only, category=category
    )

    import json

    return [
        {
            "id": a.id,
            "name": a.name,
            "trigger_phrase": a.trigger_phrase,
            "description": a.description,
            "actions": json.loads(a.actions),
            "category": a.category,
            "is_preset": a.is_preset,
            "enabled": a.enabled,
            "execution_count": a.execution_count,
            "last_executed": a.last_executed.isoformat() if a.last_executed else None,
        }
        for a in actions
    ]


@router.get("/actions/{action_id}", summary="Get quick action", description="""
Get specific quick action details.
""")
async def get_action(action_id: int, db: AsyncSession = Depends(get_db)):
    """Get a quick action"""
    service = QuickActionsService(db)
    action = await service.get_action(action_id)

    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    import json

    return {
        "id": action.id,
        "name": action.name,
        "trigger_phrase": action.trigger_phrase,
        "description": action.description,
        "actions": json.loads(action.actions),
        "category": action.category,
        "is_preset": action.is_preset,
        "enabled": action.enabled,
        "execution_count": action.execution_count,
        "last_executed": action.last_executed.isoformat()
        if action.last_executed
        else None,
        "created_at": action.created_at.isoformat(),
    }


@router.patch("/actions/{action_id}", summary="Update quick action", description="""
Update a quick action.

**Note:** Cannot modify preset actions, only custom ones.
""")
async def update_action(
    action_id: int, update: QuickActionUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a quick action"""
    service = QuickActionsService(db)

    updated = await service.update_action(
        action_id=action_id,
        name=update.name,
        trigger_phrase=update.trigger_phrase,
        actions=update.actions,
        description=update.description,
        enabled=update.enabled,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Action not found")

    import json

    return {
        "id": updated.id,
        "name": updated.name,
        "trigger_phrase": updated.trigger_phrase,
        "actions": json.loads(updated.actions),
        "enabled": updated.enabled,
    }


@router.delete("/actions/{action_id}", summary="Delete quick action", description="""
Delete a custom quick action.

**Note:** Cannot delete preset actions.
""")
async def delete_action(action_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a quick action"""
    service = QuickActionsService(db)
    success = await service.delete_action(action_id)

    if not success:
        raise HTTPException(
            status_code=404, detail="Action not found or cannot delete preset action"
        )

    return {"status": "deleted", "action_id": action_id}


@router.post("/execute/{action_id}", summary="Execute quick action by ID", description="""
Execute a quick action by its ID.

**Optional context:**
Can provide runtime context for dynamic actions.

**Returns:** Execution results for each step

**Example:**
User: "Athena, run my morning routine"
→ Executes "morning" action
→ Returns briefing, emails, calendar summary
""")
async def execute_action(
    action_id: int,
    context: Optional[Dict[str, Any]] = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """Execute a quick action"""
    service = QuickActionsService(db)
    result = await service.execute_action(action_id=action_id, context=context)

    return result


@router.post("/trigger", summary="Execute by trigger phrase", description="""
Execute a quick action by its trigger phrase.

**Example:**
```json
{
  "trigger": "morning",
  "context": {}
}
```

**JARVIS voice use:**
User: "Athena, morning"
→ JARVIS executes "morning" quick action
→ Returns briefing

**Common triggers:**
- "morning" - Morning routine
- "focus" - Start focus mode
- "wind down" - Evening routine
- "catch up" - Quick update
- "heading to office" - Commute prep
- "heading home" - End of day

**Use case:** Natural language shortcuts
""")
async def execute_by_trigger(
    trigger: str = Body(..., embed=True),
    context: Optional[Dict[str, Any]] = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """Execute action by trigger phrase"""
    service = QuickActionsService(db)
    result = await service.execute_by_trigger(trigger=trigger, context=context)

    return result


@router.post("/initialize-presets", summary="Initialize preset actions", description="""
Initialize default preset quick actions.

**Creates:**
- morning - Morning briefing routine
- focus - Start focus mode
- wind_down - Evening summary
- catch_up - Quick catch-up

**JARVIS use:** Called on first setup
""")
async def initialize_presets(db: AsyncSession = Depends(get_db)):
    """Initialize preset quick actions"""
    service = QuickActionsService(db)
    await service.initialize_preset_actions()

    return {
        "status": "initialized",
        "message": "Preset quick actions have been initialized",
    }


@router.post("/suggest", summary="Get custom action suggestion", description="""
AI-powered suggestion for custom quick action based on user behavior.

**Input:**
```json
{
  "user_behavior": {
    "pattern": "User always checks emails, then calendar, then starts focus mode on Monday mornings",
    "frequency": "weekly",
    "day": "Monday",
    "time": "09:00"
  }
}
```

**Returns:** Suggested quick action

**JARVIS proactive:**
"Sir, I noticed you always do the same sequence on Monday mornings:
 Check emails → Check calendar → Start focus mode

Should I create a quick action 'monday_start' to automate this?"

**Use case:** Learn from behavior and suggest automation
""")
async def suggest_action(
    user_behavior: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)
):
    """Get AI suggestion for custom action"""
    service = QuickActionsService(db)
    suggestion = await service.suggest_custom_action(user_behavior)

    if not suggestion:
        return {"suggestion": None, "message": "No suggestion at this time"}

    return {
        "suggestion": suggestion,
        "message": "Should I create this quick action for you?",
    }
