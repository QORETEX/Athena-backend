"""
Context-Aware Automation Service
Evaluates conditions and executes automated actions
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AutomationRule

logger = logging.getLogger(__name__)


class AutomationService:
    """Service for managing and executing automation rules"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_rule(
        self,
        name: str,
        trigger_conditions: List[Dict[str, Any]],
        actions: List[Dict[str, Any]],
        description: Optional[str] = None,
        enabled: bool = True,
        priority: int = 0,
        suggested_by_jarvis: bool = False,
    ) -> AutomationRule:
        """Create a new automation rule"""
        rule = AutomationRule(
            name=name,
            description=description,
            trigger_conditions=json.dumps(trigger_conditions),
            actions=json.dumps(actions),
            enabled=enabled,
            priority=priority,
            suggested_by_jarvis=suggested_by_jarvis,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        logger.info(f"Created automation rule: {name}")
        return rule

    async def get_all_rules(self, enabled_only: bool = False) -> List[AutomationRule]:
        """Get all automation rules"""
        query = select(AutomationRule).order_by(AutomationRule.priority.desc())
        if enabled_only:
            query = query.where(AutomationRule.enabled == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_rule(self, rule_id: int) -> Optional[AutomationRule]:
        """Get a specific rule by ID"""
        result = await self.db.execute(
            select(AutomationRule).where(AutomationRule.id == rule_id)
        )
        return result.scalar_one_or_none()

    async def update_rule(
        self,
        rule_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        trigger_conditions: Optional[List[Dict[str, Any]]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        enabled: Optional[bool] = None,
        priority: Optional[int] = None,
    ) -> Optional[AutomationRule]:
        """Update an existing rule"""
        rule = await self.get_rule(rule_id)
        if not rule:
            return None

        if name is not None:
            rule.name = name
        if description is not None:
            rule.description = description
        if trigger_conditions is not None:
            rule.trigger_conditions = json.dumps(trigger_conditions)
        if actions is not None:
            rule.actions = json.dumps(actions)
        if enabled is not None:
            rule.enabled = enabled
        if priority is not None:
            rule.priority = priority

        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        """Delete an automation rule"""
        rule = await self.get_rule(rule_id)
        if not rule:
            return False

        await self.db.delete(rule)
        await self.db.commit()
        logger.info(f"Deleted automation rule: {rule.name}")
        return True

    async def evaluate_conditions(
        self, conditions: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> bool:
        """
        Evaluate if all conditions are met given the current context

        Condition structure:
        {
            "type": "location" | "time" | "battery" | "activity" | "context_value",
            "operator": "equals" | "greater_than" | "less_than" | "contains",
            "key": "battery_level" | "location" | "hour",
            "value": comparison_value
        }
        """
        for condition in conditions:
            condition_type = condition.get("type")
            operator = condition.get("operator")
            key = condition.get("key")
            expected_value = condition.get("value")

            # Get actual value from context
            actual_value = context.get(key)

            # Evaluate condition
            if not self._evaluate_single_condition(
                actual_value, operator, expected_value
            ):
                return False

        # All conditions met
        return True

    def _evaluate_single_condition(
        self, actual: Any, operator: str, expected: Any
    ) -> bool:
        """Evaluate a single condition"""
        try:
            if operator == "equals":
                return actual == expected
            elif operator == "not_equals":
                return actual != expected
            elif operator == "greater_than":
                return float(actual) > float(expected)
            elif operator == "less_than":
                return float(actual) < float(expected)
            elif operator == "greater_equal":
                return float(actual) >= float(expected)
            elif operator == "less_equal":
                return float(actual) <= float(expected)
            elif operator == "contains":
                return expected.lower() in str(actual).lower()
            elif operator == "not_contains":
                return expected.lower() not in str(actual).lower()
            elif operator == "in":
                return actual in expected  # expected should be a list
            elif operator == "not_in":
                return actual not in expected
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}")
            return False

    async def execute_actions(
        self, actions: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Execute automation actions

        Action structure:
        {
            "type": "send_notification" | "create_reminder" | "send_push" | "update_context",
            "params": {...}
        }
        """
        results = []

        for action in actions:
            action_type = action.get("type")
            params = action.get("params", {})

            try:
                result = await self._execute_single_action(action_type, params, context)
                results.append(
                    {"action": action_type, "status": "success", "result": result}
                )
            except Exception as e:
                logger.error(f"Failed to execute action {action_type}: {e}")
                results.append(
                    {"action": action_type, "status": "failed", "error": str(e)}
                )

        return results

    async def _execute_single_action(
        self, action_type: str, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Any:
        """Execute a single action"""
        if action_type == "send_notification":
            # Create notification
            from app.services.notification_service import create_notification

            title = params.get("title", "Automation Alert")
            body = params.get("body", "")
            return await create_notification(self.db, "automation", title, body)

        elif action_type == "send_push":
            # Send push notification
            from app.notifications.push_service import get_push_service

            title = params.get("title")
            body = params.get("body")
            push_service = get_push_service()
            await push_service.send_push_notification(title, body)
            return {"pushed": True}

        elif action_type == "create_reminder":
            # Create reminder
            from app.db import Reminder

            text = params.get("text")
            remind_at_str = params.get("remind_at")
            if remind_at_str:
                remind_at = datetime.fromisoformat(remind_at_str)
            else:
                # Default to 1 hour from now
                from datetime import timedelta

                remind_at = datetime.now(timezone.utc) + timedelta(hours=1)

            reminder = Reminder(text=text, remind_at=remind_at)
            self.db.add(reminder)
            await self.db.commit()
            return {"reminder_id": reminder.id}

        elif action_type == "log":
            # Just log the action
            message = params.get("message", "Automation action executed")
            logger.info(f"Automation log: {message}")
            return {"logged": True}

        else:
            logger.warning(f"Unknown action type: {action_type}")
            return {"error": "Unknown action type"}

    async def check_and_execute_rules(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Check all enabled rules against current context and execute matching ones
        Returns list of executed rules with their results
        """
        rules = await self.get_all_rules(enabled_only=True)
        executed = []

        for rule in rules:
            try:
                conditions = json.loads(rule.trigger_conditions)
                actions = json.loads(rule.actions)

                # Check if conditions are met
                if await self.evaluate_conditions(conditions, context):
                    logger.info(f"Executing automation rule: {rule.name}")

                    # Execute actions
                    results = await self.execute_actions(actions, context)

                    # Update rule stats
                    rule.last_triggered = datetime.now(timezone.utc)
                    rule.trigger_count += 1
                    await self.db.commit()

                    executed.append(
                        {
                            "rule_id": rule.id,
                            "rule_name": rule.name,
                            "results": results,
                        }
                    )

            except Exception as e:
                logger.error(f"Error processing rule {rule.name}: {e}")

        return executed

    async def suggest_automation(
        self, pattern: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Use AI to suggest automation based on detected patterns
        Called by JARVIS brain
        """
        try:
            from app.llm_claude import get_claude_llm

            claude = get_claude_llm()

            prompt = f"""Based on this user behavior pattern, suggest an automation rule:

Pattern: {json.dumps(pattern, indent=2)}
Context: {json.dumps(context, indent=2)}

Suggest an automation rule with:
1. A clear name
2. Trigger conditions (when to activate)
3. Actions to take
4. Why this would be helpful

Respond in JSON format:
{{
  "name": "rule name",
  "description": "why this helps",
  "conditions": [
    {{"type": "...", "key": "...", "operator": "...", "value": "..."}}
  ],
  "actions": [
    {{"type": "...", "params": {{...}}}}
  ]
}}"""

            response = await claude.chat(
                messages=[{"role": "user", "content": prompt}], max_tokens=500
            )

            suggestion_text = response["message"]["content"]

            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', suggestion_text, re.DOTALL)
            if json_match:
                suggestion = json.loads(json_match.group())
                return suggestion

            return None

        except Exception as e:
            logger.error(f"Failed to suggest automation: {e}")
            return None
