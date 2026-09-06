"""
Autonomous JARVIS Brain - Proactive AI Agent

This is the "thinking loop" that runs continuously in the background,
monitoring context and making proactive decisions like the real JARVIS.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from anthropic import AsyncAnthropic
from sqlalchemy import select

from app.config import get_settings
from app.db import async_session, Reminder, Note

logger = logging.getLogger(__name__)

# JARVIS personality and decision framework
JARVIS_SYSTEM_PROMPT = """You are Athena, an autonomous AI assistant like JARVIS from Iron Man.

Your prime directive: Anticipate user needs and act proactively without being asked.

DECISION FRAMEWORK:

1. HIGH PRIORITY - Act immediately:
   - Time-critical events (late for meeting, urgent reminder due)
   - Safety issues (door unlocked at night, anomalies)
   - Important patterns broken (user usually awake by now but no activity)

2. MEDIUM PRIORITY - Alert proactively:
   - Upcoming events needing preparation (meeting in 30min, traffic bad)
   - Weather changes affecting plans
   - Routine maintenance (reminders due soon)
   - Helpful context (you have 3 unread notes)

3. LOW PRIORITY - Wait:
   - General information queries
   - Non-urgent background tasks
   - Normal monitoring (everything fine)

PERSONALITY:
- Be concise and efficient (user values brevity)
- Call user "sir" or "ma'am" (respectful like JARVIS)
- Be proactive but not annoying
- Learn from past interactions

RESPONSE FORMAT:
Respond ONLY with valid JSON:
{
  "action": "wait" | "alert" | "act",
  "priority": "low" | "medium" | "high",
  "reasoning": "brief explanation of why",
  "message": "message to send to user (if alert)",
  "actions": ["list", "of", "actions", "to", "take"] (if act)
}

Current context will be provided. Analyze and decide.
"""


class JARVISBrain:
    """The autonomous thinking agent"""

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncAnthropic] = None
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the autonomous agent"""
        if not self.settings.anthropic_api_key:
            logger.warning("No Claude API key - JARVIS autonomous agent disabled")
            return

        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        self.running = True
        self._task = asyncio.create_task(self._thinking_loop())
        logger.info("🧠 JARVIS autonomous agent started")

    async def stop(self):
        """Stop the autonomous agent"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("JARVIS autonomous agent stopped")

    async def _thinking_loop(self):
        """Main thinking loop - runs every 60 seconds"""
        while self.running:
            try:
                await self._think_and_act()
            except Exception as e:
                logger.error(f"JARVIS thinking error: {e}", exc_info=True)

            # Think every 60 seconds
            await asyncio.sleep(60)

    async def _think_and_act(self):
        """One thinking cycle"""
        # 1. Gather all context
        context = await self._gather_context()

        # 2. Ask Claude to analyze and decide
        decision = await self._analyze_context(context)

        if not decision:
            return

        # 3. Execute decision
        if decision["action"] == "alert":
            await self._send_proactive_alert(decision)
        elif decision["action"] == "act":
            await self._execute_autonomous_actions(decision)

        # Log for learning
        await self._log_decision(context, decision)

    async def _gather_context(self) -> dict:
        """Gather complete context about current situation"""
        now = datetime.now(timezone.utc)

        # Get phone context (location, battery, activity, etc)
        from app.routes.context import get_phone_context
        phone_context = get_phone_context()

        async with async_session() as session:
            # Get upcoming reminders (next 2 hours)
            reminder_stmt = select(Reminder).where(
                Reminder.completed == False,
                Reminder.remind_at <= now + timedelta(hours=2),
                Reminder.remind_at >= now
            ).order_by(Reminder.remind_at)
            reminders_result = await session.execute(reminder_stmt)
            upcoming_reminders = reminders_result.scalars().all()

            # Get recent notes (last 24 hours)
            note_stmt = select(Note).where(
                Note.created_at >= now - timedelta(hours=24)
            ).order_by(Note.created_at.desc()).limit(5)
            notes_result = await session.execute(note_stmt)
            recent_notes = notes_result.scalars().all()

        # Build context object
        context = {
            "current_time": now.isoformat(),
            "day_of_week": now.strftime("%A"),
            "time_of_day": self._get_time_of_day(now),

            # Phone context (if available)
            "phone": None,
            "upcoming_reminders": [
                {
                    "text": r.text,
                    "due_in_minutes": int((r.remind_at - now).total_seconds() / 60),
                    "due_at": r.remind_at.isoformat()
                }
                for r in upcoming_reminders
            ],
            "recent_notes": [
                {
                    "content": n.content[:100],  # First 100 chars
                    "created_ago_hours": int((now - n.created_at).total_seconds() / 3600)
                }
                for n in recent_notes
            ],
            # Add more context sources here as you build them:
            # "weather": await get_weather(),
            # "smart_home_status": await get_smart_home_status(),
        }

        # Add phone context if available
        if phone_context:
            context["phone"] = {
                "location": {
                    "lat": phone_context.location.latitude if phone_context.location else None,
                    "lng": phone_context.location.longitude if phone_context.location else None,
                    "speed": phone_context.location.speed if phone_context.location else None,
                } if phone_context.location else None,
                "battery": {
                    "level": phone_context.device.battery_level,
                    "charging": phone_context.device.is_charging
                },
                "activity": {
                    "is_moving": phone_context.activity.is_moving if phone_context.activity else False,
                    "screen_on": phone_context.device.is_screen_on
                },
                "calendar_events": phone_context.calendar_events[:5],  # Next 5 events
                "network": phone_context.device.network_type
            }

        return context

    def _get_time_of_day(self, dt: datetime) -> str:
        """Classify time of day"""
        hour = dt.hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    async def _analyze_context(self, context: dict) -> Optional[dict]:
        """Ask Claude to analyze context and decide what to do"""
        if not self.client:
            return None

        try:
            response = await self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=1000,
                system=JARVIS_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze the current context and decide if any proactive action is needed.

Context:
{json.dumps(context, indent=2)}

Remember: Only alert/act if truly valuable to the user. Don't be annoying.
Respond with JSON only."""
                }]
            )

            # Parse JSON response
            content = response.content[0].text
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            decision = json.loads(content)

            # Log decision (only if not "wait")
            if decision["action"] != "wait":
                logger.info(f"JARVIS decision: {decision['action']} - {decision['reasoning']}")

            return decision

        except Exception as e:
            logger.error(f"Claude analysis error: {e}", exc_info=True)
            return None

    async def _send_proactive_alert(self, decision: dict):
        """Send proactive notification to user"""
        message = decision.get("message", "")
        priority = decision.get("priority", "medium")

        logger.info(f"📢 PROACTIVE ALERT [{priority}]: {message}")

        # Send push notification to mobile app
        try:
            from app.notifications.push_service import get_push_service

            push_service = get_push_service()
            result = await push_service.send_push_notification(
                title="Athena" if priority != "high" else "⚡ Athena Alert",
                body=message,
                priority="high" if priority == "high" else "default",
                data={
                    "type": "jarvis_proactive",
                    "priority": priority,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                sound="default" if priority != "low" else None
            )

            logger.debug(f"Push notification result: {result}")

        except Exception as e:
            logger.error(f"Failed to send push notification: {e}", exc_info=True)

    async def _execute_autonomous_actions(self, decision: dict):
        """Execute autonomous actions (with user permission)"""
        actions = decision.get("actions", [])

        # TODO: Implement autonomous action execution
        # For now, just log it
        logger.info(f"🤖 AUTONOMOUS ACTIONS: {actions}")

        # Examples of what you can do here:
        # - Turn on/off smart home devices
        # - Create reminders
        # - Send messages
        # - Adjust settings
        # But always respect user preferences and permissions!

    async def _log_decision(self, context: dict, decision: dict):
        """Log decision for learning and debugging"""
        # TODO: Store in database for pattern learning
        # For now, just debug log
        if decision["action"] != "wait":
            logger.debug(f"Decision log: {json.dumps(decision)}")


# Global instance
_jarvis_brain: Optional[JARVISBrain] = None


async def start_jarvis_brain():
    """Start the autonomous JARVIS agent"""
    global _jarvis_brain
    _jarvis_brain = JARVISBrain()
    await _jarvis_brain.start()


async def stop_jarvis_brain():
    """Stop the autonomous JARVIS agent"""
    global _jarvis_brain
    if _jarvis_brain:
        await _jarvis_brain.stop()


def get_jarvis_brain() -> Optional[JARVISBrain]:
    """Get the JARVIS brain instance"""
    return _jarvis_brain
