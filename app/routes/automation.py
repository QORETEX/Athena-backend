"""
Context-Aware Automation Routes
Create and manage automation rules
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.automation_service import AutomationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])


class AutomationRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_conditions: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    enabled: bool = True
    priority: int = 0


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_conditions: Optional[List[Dict[str, Any]]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class ContextInput(BaseModel):
    context: Dict[str, Any]


@router.post("/rules", summary="Create automation rule", description="""
Create a context-aware automation rule.

**Example rule:**
```json
{
  "name": "Charge Reminder",
  "description": "Remind to charge when arriving home with low battery",
  "trigger_conditions": [
    {"type": "location", "key": "location", "operator": "equals", "value": "home"},
    {"type": "battery", "key": "battery_level", "operator": "less_than", "value": 20}
  ],
  "actions": [
    {"type": "send_push", "params": {"title": "Charge Phone", "body": "Battery low, please charge"}}
  ],
  "enabled": true,
  "priority": 5
}
```

**Condition operators:**
- equals, not_equals
- greater_than, less_than, greater_equal, less_equal
- contains, not_contains
- in, not_in

**Action types:**
- send_notification - Create system notification
- send_push - Send push notification to mobile
- create_reminder - Create timed reminder
- log - Log message

**JARVIS use:**
Automatically executes rules when conditions match, creating a truly automated assistant.

**Use case:**
"When I'm driving AND receive urgent email, read it aloud"
"Every Monday at 8 AM, prepare weekly briefing"
""")
async def create_rule(
    rule: AutomationRuleCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new automation rule"""
    service = AutomationService(db)

    created_rule = await service.create_rule(
        name=rule.name,
        trigger_conditions=rule.trigger_conditions,
        actions=rule.actions,
        description=rule.description,
        enabled=rule.enabled,
        priority=rule.priority,
    )

    return {
        "id": created_rule.id,
        "name": created_rule.name,
        "description": created_rule.description,
        "enabled": created_rule.enabled,
        "priority": created_rule.priority,
        "trigger_count": created_rule.trigger_count,
    }


@router.get("/rules", summary="List automation rules", description="""
Get all automation rules.

**Query parameters:**
- `enabled_only` - Only return enabled rules

**Returns:** List of all automation rules with their conditions and actions

**JARVIS use:** Displays active automations to user
""")
async def list_rules(enabled_only: bool = False, db: AsyncSession = Depends(get_db)):
    """List all automation rules"""
    service = AutomationService(db)
    rules = await service.get_all_rules(enabled_only=enabled_only)

    import json

    return [
        {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "trigger_conditions": json.loads(rule.trigger_conditions),
            "actions": json.loads(rule.actions),
            "enabled": rule.enabled,
            "priority": rule.priority,
            "trigger_count": rule.trigger_count,
            "last_triggered": rule.last_triggered.isoformat()
            if rule.last_triggered
            else None,
            "suggested_by_jarvis": rule.suggested_by_jarvis,
        }
        for rule in rules
    ]


@router.get("/rules/{rule_id}", summary="Get automation rule", description="""
Get specific automation rule details.

**Returns:** Full rule definition with execution history
""")
async def get_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific automation rule"""
    service = AutomationService(db)
    rule = await service.get_rule(rule_id)

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    import json

    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "trigger_conditions": json.loads(rule.trigger_conditions),
        "actions": json.loads(rule.actions),
        "enabled": rule.enabled,
        "priority": rule.priority,
        "trigger_count": rule.trigger_count,
        "last_triggered": rule.last_triggered.isoformat()
        if rule.last_triggered
        else None,
        "suggested_by_jarvis": rule.suggested_by_jarvis,
        "created_at": rule.created_at.isoformat(),
    }


@router.patch("/rules/{rule_id}", summary="Update automation rule", description="""
Update an existing automation rule.

**Updatable fields:**
- name
- description
- trigger_conditions
- actions
- enabled (activate/deactivate)
- priority

**JARVIS use:** Allows user to modify or disable automation rules
""")
async def update_rule(
    rule_id: int, update: AutomationRuleUpdate, db: AsyncSession = Depends(get_db)
):
    """Update an automation rule"""
    service = AutomationService(db)

    updated_rule = await service.update_rule(
        rule_id=rule_id,
        name=update.name,
        description=update.description,
        trigger_conditions=update.trigger_conditions,
        actions=update.actions,
        enabled=update.enabled,
        priority=update.priority,
    )

    if not updated_rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    import json

    return {
        "id": updated_rule.id,
        "name": updated_rule.name,
        "description": updated_rule.description,
        "trigger_conditions": json.loads(updated_rule.trigger_conditions),
        "actions": json.loads(updated_rule.actions),
        "enabled": updated_rule.enabled,
        "priority": updated_rule.priority,
    }


@router.delete("/rules/{rule_id}", summary="Delete automation rule", description="""
Delete an automation rule permanently.

**JARVIS use:** Removes unwanted automation
""")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an automation rule"""
    service = AutomationService(db)
    success = await service.delete_rule(rule_id)

    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")

    return {"status": "deleted", "rule_id": rule_id}


@router.post("/evaluate", summary="Evaluate rules against context", description="""
Check all enabled rules against current context and execute matching ones.

**Input:** Current context (location, battery, time, activity, etc.)

**Example context:**
```json
{
  "context": {
    "location": "home",
    "battery_level": 15,
    "hour": 22,
    "activity": "idle",
    "is_driving": false
  }
}
```

**Returns:** List of executed rules and their results

**JARVIS use:** Called periodically by JARVIS brain to check and execute automation rules
""")
async def evaluate_rules(input: ContextInput, db: AsyncSession = Depends(get_db)):
    """Evaluate all rules against current context"""
    service = AutomationService(db)
    executed = await service.check_and_execute_rules(input.context)

    return {
        "evaluated_at": "now",
        "rules_executed": len(executed),
        "results": executed,
    }


@router.post("/suggest", summary="Get automation suggestions", description="""
AI-powered automation suggestions based on user patterns.

**Input:** Pattern data and context

**Example:**
```json
{
  "pattern": {
    "type": "repeated_action",
    "description": "User always turns off lights when leaving home",
    "frequency": "daily"
  },
  "context": {
    "location_history": [...],
    "recent_actions": [...]
  }
}
```

**Returns:** Suggested automation rule that JARVIS can create

**JARVIS use:** Proactively suggests useful automations
"Sir, I noticed you always do X when Y. Should I automate this?"
""")
async def suggest_automation(
    pattern: Dict[str, Any] = Body(...),
    context: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Get AI suggestion for automation"""
    service = AutomationService(db)
    suggestion = await service.suggest_automation(pattern, context)

    if not suggestion:
        return {"suggestion": None, "message": "No automation suggestion at this time"}

    return {"suggestion": suggestion, "message": "Create this automation?"}
