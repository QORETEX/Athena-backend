"""
Quick Actions Service
Execute multi-step shortcuts with single commands
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import QuickAction

logger = logging.getLogger(__name__)


class QuickActionsService:
    """Service for managing and executing quick actions/shortcuts"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_action(
        self,
        name: str,
        trigger_phrase: str,
        actions: List[Dict[str, Any]],
        description: Optional[str] = None,
        category: str = "custom",
        is_preset: bool = False,
    ) -> QuickAction:
        """Create a new quick action"""
        action = QuickAction(
            name=name,
            trigger_phrase=trigger_phrase.lower(),
            description=description,
            actions=json.dumps(actions),
            category=category,
            is_preset=is_preset,
        )
        self.db.add(action)
        await self.db.commit()
        await self.db.refresh(action)
        logger.info(f"Created quick action: {name}")
        return action

    async def get_all_actions(
        self, enabled_only: bool = False, category: Optional[str] = None
    ) -> List[QuickAction]:
        """Get all quick actions"""
        query = select(QuickAction).order_by(QuickAction.name)

        if enabled_only:
            query = query.where(QuickAction.enabled == True)

        if category:
            query = query.where(QuickAction.category == category)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_action(self, action_id: int) -> Optional[QuickAction]:
        """Get a specific quick action"""
        result = await self.db.execute(
            select(QuickAction).where(QuickAction.id == action_id)
        )
        return result.scalar_one_or_none()

    async def get_action_by_trigger(self, trigger: str) -> Optional[QuickAction]:
        """Get action by trigger phrase"""
        result = await self.db.execute(
            select(QuickAction).where(
                QuickAction.trigger_phrase == trigger.lower(),
                QuickAction.enabled == True,
            )
        )
        return result.scalar_one_or_none()

    async def update_action(
        self,
        action_id: int,
        name: Optional[str] = None,
        trigger_phrase: Optional[str] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[QuickAction]:
        """Update a quick action"""
        action = await self.get_action(action_id)
        if not action:
            return None

        if name is not None:
            action.name = name
        if trigger_phrase is not None:
            action.trigger_phrase = trigger_phrase.lower()
        if actions is not None:
            action.actions = json.dumps(actions)
        if description is not None:
            action.description = description
        if enabled is not None:
            action.enabled = enabled

        await self.db.commit()
        await self.db.refresh(action)
        return action

    async def delete_action(self, action_id: int) -> bool:
        """Delete a quick action"""
        action = await self.get_action(action_id)
        if not action:
            return False

        # Don't allow deleting preset actions
        if action.is_preset:
            logger.warning(f"Cannot delete preset action: {action.name}")
            return False

        await self.db.delete(action)
        await self.db.commit()
        logger.info(f"Deleted quick action: {action.name}")
        return True

    async def execute_action(
        self, action_id: int, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a quick action's steps"""
        action = await self.get_action(action_id)
        if not action or not action.enabled:
            return {"success": False, "error": "Action not found or disabled"}

        logger.info(f"Executing quick action: {action.name}")

        actions = json.loads(action.actions)
        results = []
        errors = []

        for step in actions:
            try:
                result = await self._execute_step(step, context or {})
                results.append(result)
            except Exception as e:
                error_msg = f"Step failed: {step.get('type')} - {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Update execution stats
        action.execution_count += 1
        action.last_executed = datetime.now(timezone.utc)
        await self.db.commit()

        return {
            "success": len(errors) == 0,
            "action_name": action.name,
            "results": results,
            "errors": errors,
        }

    async def execute_by_trigger(
        self, trigger: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute action by trigger phrase"""
        action = await self.get_action_by_trigger(trigger)
        if not action:
            return {"success": False, "error": f"No action found for trigger: {trigger}"}

        return await self.execute_action(action.id, context)

    async def _execute_step(
        self, step: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single action step"""
        step_type = step.get("type")
        params = step.get("params", {})

        if step_type == "send_notification":
            # Log notification (push service requires expo tokens)
            title = params.get("title", "Quick Action")
            body = params.get("body", "Action executed")
            logger.info(f"Notification: {title} - {body}")

            # Try to send push if tokens exist
            try:
                from app.notifications.push_service import ExpoPushService
                push_service = ExpoPushService()
                await push_service.send_push_notification(title, body)
            except Exception as e:
                logger.debug(f"Push notification skipped: {e}")

            return {"type": "notification", "title": title, "body": body}

        elif step_type == "create_reminder":
            from app.db import Reminder
            from datetime import timedelta

            text = params.get("text")
            hours_from_now = params.get("hours_from_now", 1)
            remind_at = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)

            reminder = Reminder(text=text, remind_at=remind_at)
            self.db.add(reminder)
            await self.db.commit()
            return {"type": "reminder", "reminder_id": reminder.id}

        elif step_type == "start_focus_mode":
            from app.services.focus_service import FocusService

            focus_service = FocusService(self.db)
            duration = params.get("duration_minutes", 60)
            session = await focus_service.start_focus_session(
                focus_type=params.get("focus_type", "deep_work"),
                planned_duration_minutes=duration,
                activity=params.get("activity"),
            )
            return {"type": "focus_mode", "session_id": session.id, "started": True}

        elif step_type == "get_briefing":
            # Generate simple briefing from available data
            from app.db import Reminder, Note, Meeting

            now = datetime.now(timezone.utc)

            # Get today's reminders
            result = await self.db.execute(
                select(Reminder).where(
                    Reminder.remind_at >= now,
                    Reminder.completed == False
                ).limit(5)
            )
            reminders = list(result.scalars().all())

            # Get recent notes
            result = await self.db.execute(
                select(Note).order_by(Note.created_at.desc()).limit(3)
            )
            notes = list(result.scalars().all())

            # Get today's meetings
            result = await self.db.execute(
                select(Meeting).where(
                    Meeting.start_time >= now
                ).order_by(Meeting.start_time).limit(5)
            )
            meetings = list(result.scalars().all())

            briefing_text = f"Good morning! You have {len(reminders)} reminders, {len(meetings)} meetings today, and {len(notes)} recent notes."

            return {"type": "briefing", "content": briefing_text, "reminders": len(reminders), "meetings": len(meetings)}

        elif step_type == "check_emails":
            # Get recent urgent emails
            from app.db import Email

            result = await self.db.execute(
                select(Email)
                .where(Email.is_urgent == True, Email.is_read == False)
                .limit(5)
            )
            urgent_emails = list(result.scalars().all())
            return {
                "type": "emails",
                "urgent_count": len(urgent_emails),
                "emails": [
                    {"subject": e.subject, "sender": e.sender} for e in urgent_emails
                ],
            }

        elif step_type == "check_calendar":
            # Get next meeting
            from app.db import Meeting

            now = datetime.now(timezone.utc)
            result = await self.db.execute(
                select(Meeting)
                .where(Meeting.start_time >= now)
                .order_by(Meeting.start_time)
                .limit(1)
            )
            next_meeting = result.scalar_one_or_none()

            if next_meeting:
                return {
                    "type": "calendar",
                    "next_meeting": {
                        "title": next_meeting.title,
                        "start_time": next_meeting.start_time.isoformat(),
                    },
                }
            else:
                return {"type": "calendar", "next_meeting": None}

        elif step_type == "log":
            message = params.get("message", "Action step executed")
            logger.info(f"Quick action log: {message}")
            return {"type": "log", "message": message}

        else:
            logger.warning(f"Unknown step type: {step_type}")
            return {"type": "unknown", "error": f"Unknown step type: {step_type}"}

    async def initialize_preset_actions(self):
        """Initialize preset quick actions"""
        presets = [
            {
                "name": "morning",
                "trigger_phrase": "morning",
                "description": "Morning routine: briefing, check emails, check calendar",
                "actions": [
                    {"type": "get_briefing", "params": {}},
                    {"type": "check_emails", "params": {}},
                    {"type": "check_calendar", "params": {}},
                    {
                        "type": "send_notification",
                        "params": {
                            "title": "Good Morning",
                            "body": "Your briefing is ready",
                        },
                    },
                ],
                "category": "preset",
            },
            {
                "name": "focus",
                "trigger_phrase": "focus",
                "description": "Start deep work: enable focus mode, block notifications",
                "actions": [
                    {
                        "type": "start_focus_mode",
                        "params": {
                            "focus_type": "deep_work",
                            "duration_minutes": 60,
                            "activity": "Deep work session",
                        },
                    },
                    {"type": "log", "params": {"message": "Focus mode activated"}},
                ],
                "category": "preset",
            },
            {
                "name": "wind_down",
                "trigger_phrase": "wind down",
                "description": "Evening wind down: summary, prepare for tomorrow",
                "actions": [
                    {"type": "check_emails", "params": {}},
                    {"type": "check_calendar", "params": {}},
                    {
                        "type": "send_notification",
                        "params": {
                            "title": "Evening Summary",
                            "body": "Ready to wind down for the day",
                        },
                    },
                ],
                "category": "preset",
            },
            {
                "name": "catch_up",
                "trigger_phrase": "catch up",
                "description": "Quick catch up: emails, calendar, notifications",
                "actions": [
                    {"type": "check_emails", "params": {}},
                    {"type": "check_calendar", "params": {}},
                    {
                        "type": "send_notification",
                        "params": {
                            "title": "Catch Up Complete",
                            "body": "You're all caught up",
                        },
                    },
                ],
                "category": "preset",
            },
        ]

        for preset in presets:
            # Check if already exists
            existing = await self.get_action_by_trigger(preset["trigger_phrase"])
            if not existing:
                await self.create_action(
                    name=preset["name"],
                    trigger_phrase=preset["trigger_phrase"],
                    description=preset["description"],
                    actions=preset["actions"],
                    category=preset["category"],
                    is_preset=True,
                )
                logger.info(f"Initialized preset action: {preset['name']}")

    async def suggest_custom_action(
        self, user_behavior: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest custom quick action based on repeated behavior
        Called by JARVIS
        """
        try:
            from app.llm_claude import get_claude_llm

            claude = get_claude_llm()

            prompt = f"""Based on this user behavior pattern, suggest a quick action shortcut:

Behavior: {json.dumps(user_behavior, indent=2)}

Suggest a quick action with:
1. A short trigger phrase (1-2 words)
2. A descriptive name
3. List of steps to automate
4. Why this would be useful

Respond in JSON format:
{{
  "name": "action name",
  "trigger_phrase": "trigger",
  "description": "what it does",
  "actions": [
    {{"type": "...", "params": {{...}}}}
  ],
  "reason": "why this helps"
}}"""

            response = await claude.chat(
                messages=[{"role": "user", "content": prompt}], max_tokens=400
            )

            suggestion_text = response["message"]["content"]

            # Extract JSON
            import re

            json_match = re.search(r"\{.*\}", suggestion_text, re.DOTALL)
            if json_match:
                suggestion = json.loads(json_match.group())
                return suggestion

            return None

        except Exception as e:
            logger.error(f"Failed to suggest custom action: {e}")
            return None
