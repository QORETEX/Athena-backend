from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.triggers.cron import CronTrigger

from app.schemas import MessageType

logger = logging.getLogger(__name__)


async def execute_routine(routine_id: int) -> dict:
    """Load a routine from DB and execute its action chain sequentially."""
    from app.db import Routine, async_session

    if async_session is None:
        return {"error": "Database not initialized"}

    async with async_session() as session:
        routine = await session.get(Routine, routine_id)
        if not routine:
            logger.warning("Routine %d not found", routine_id)
            return {"error": f"Routine {routine_id} not found"}

        if not routine.enabled:
            logger.info("Routine %d (%s) is disabled, skipping", routine_id, routine.name)
            return {"skipped": True, "reason": "disabled"}

        try:
            actions = json.loads(routine.actions)
        except (json.JSONDecodeError, TypeError):
            logger.error("Routine %d has invalid actions JSON", routine_id)
            return {"error": "Invalid actions configuration"}

        logger.info("Executing routine %d: %s (%d actions)", routine_id, routine.name, len(actions))

        results = []
        for i, action in enumerate(actions):
            action_type = action.get("type", "")
            config = action.get("config", {})

            try:
                result = await _execute_action(action_type, config)
                results.append({"action": action_type, "index": i, "result": result})
            except Exception as exc:
                logger.exception("Routine %d action %d (%s) failed", routine_id, i, action_type)
                results.append({"action": action_type, "index": i, "error": str(exc)})

        routine.last_triggered = datetime.now(timezone.utc)
        await session.commit()

    return {"routine_id": routine_id, "actions_executed": len(results), "results": results}


async def _execute_action(action_type: str, config: dict) -> dict:
    """Dispatch a single action by type."""
    if action_type == "smart_home":
        return await _action_smart_home(config)
    elif action_type == "notification":
        return await _action_notification(config)
    elif action_type == "skill":
        return await _action_skill(config)
    elif action_type == "briefing":
        return await _action_briefing(config)
    else:
        return {"error": f"Unknown action type: {action_type}"}


async def _action_smart_home(config: dict) -> dict:
    from app.skills.smart_home import handle_smart_home

    entity_id = config.get("entity_id", "")
    action = config.get("action", "toggle")
    if not entity_id:
        return {"error": "entity_id required for smart_home action"}
    return await handle_smart_home(entity_id=entity_id, action=action)


async def _action_notification(config: dict) -> dict:
    from app.websocket.events import broadcast_event

    title = config.get("title", "Routine triggered")
    body = config.get("body", "")
    priority = config.get("priority", "normal")

    await broadcast_event(MessageType.REMINDER_DUE, {
        "event_type": "routine_notification",
        "title": title,
        "body": body,
        "priority": priority,
    })
    return {"sent": True}


async def _action_skill(config: dict) -> dict:
    from app.skills.base import get_skill

    skill_name = config.get("skill_name", "")
    skill_args = config.get("args", {})
    if not skill_name:
        return {"error": "skill_name required for skill action"}

    skill = get_skill(skill_name)
    if not skill:
        return {"error": f"Skill '{skill_name}' not found"}
    if skill.client_executed:
        return {"error": f"Skill '{skill_name}' is client-executed and cannot be automated"}
    if not skill.handler:
        return {"error": f"Skill '{skill_name}' has no handler"}

    result = await asyncio.wait_for(skill.handler(**skill_args), timeout=skill.timeout)
    return result if isinstance(result, dict) else {"result": str(result)}


async def _action_briefing(config: dict) -> dict:
    try:
        from app.routes.briefing import generate_briefing
        return await generate_briefing()
    except ImportError:
        return {"error": "Briefing module not available"}
    except Exception as exc:
        return {"error": f"Briefing failed: {exc}"}


def _build_cron_trigger(trigger_config: dict) -> Optional[CronTrigger]:
    """Build an APScheduler CronTrigger from routine trigger_config."""
    hour = trigger_config.get("hour", "*")
    minute = trigger_config.get("minute", 0)
    day_of_week = trigger_config.get("days_of_week", "*")

    if isinstance(day_of_week, list):
        day_of_week = ",".join(str(d) for d in day_of_week)

    return CronTrigger(hour=hour, minute=minute, day_of_week=day_of_week)


def register_routine(routine_id: int, name: str, trigger_type: str, trigger_config_str: str):
    """Register a routine's trigger with the APScheduler."""
    from app.scheduler import scheduler

    if scheduler is None:
        logger.warning("Scheduler not running — cannot register routine %d", routine_id)
        return

    try:
        trigger_config = json.loads(trigger_config_str)
    except (json.JSONDecodeError, TypeError):
        logger.error("Routine %d has invalid trigger_config JSON", routine_id)
        return

    job_id = f"routine_{routine_id}"

    if trigger_type == "time":
        trigger = _build_cron_trigger(trigger_config)
        if trigger is None:
            return

        def _run_routine():
            asyncio.ensure_future(execute_routine(routine_id))

        scheduler.add_job(
            _run_routine,
            trigger,
            id=job_id,
            replace_existing=True,
            name=f"Routine: {name}",
        )
        logger.info("Registered time-triggered routine %d (%s)", routine_id, name)

    elif trigger_type in ("event", "sunset", "sunrise"):
        logger.info(
            "Routine %d (%s) uses trigger '%s' — will be dispatched by proactive monitor",
            routine_id, name, trigger_type,
        )
    else:
        logger.warning("Routine %d has unknown trigger_type: %s", routine_id, trigger_type)


def unregister_routine(routine_id: int):
    """Remove a routine's trigger from the scheduler."""
    from app.scheduler import scheduler

    if scheduler is None:
        return

    job_id = f"routine_{routine_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info("Unregistered routine %d from scheduler", routine_id)
    except Exception:
        pass


async def load_routines():
    """Load all enabled routines from DB and schedule time-based triggers."""
    from app.db import Routine, async_session

    if async_session is None:
        logger.warning("Database not initialized — skipping routine loading")
        return

    try:
        from sqlalchemy import select

        async with async_session() as session:
            stmt = select(Routine).where(Routine.enabled == True)  # noqa: E712
            result = await session.execute(stmt)
            routines = result.scalars().all()

            count = 0
            for routine in routines:
                register_routine(
                    routine.id,
                    routine.name,
                    routine.trigger_type,
                    routine.trigger_config,
                )
                count += 1

            logger.info("Loaded %d routines from database", count)
    except Exception:
        logger.exception("Failed to load routines from database")


async def trigger_event_routines(event_name: str, event_data: dict | None = None):
    """Trigger all event-based routines that match the given event name."""
    from app.db import Routine, async_session

    if async_session is None:
        return

    try:
        from sqlalchemy import select

        async with async_session() as session:
            stmt = select(Routine).where(
                Routine.enabled == True,  # noqa: E712
                Routine.trigger_type == "event",
            )
            result = await session.execute(stmt)
            routines = result.scalars().all()

            for routine in routines:
                try:
                    trigger_config = json.loads(routine.trigger_config)
                except (json.JSONDecodeError, TypeError):
                    continue

                if trigger_config.get("event_name") == event_name:
                    logger.info("Event '%s' matched routine %d (%s)", event_name, routine.id, routine.name)
                    asyncio.ensure_future(execute_routine(routine.id))
    except Exception:
        logger.exception("Error triggering event routines for '%s'", event_name)
