from __future__ import annotations

import logging

from app.availability import is_reachable
from app.config import get_settings
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)


async def handle_background_research(topic: str, task_type: str = "research") -> dict:
    from app.tasks.runner import submit_task

    if task_type not in ("research", "analysis", "summary"):
        task_type = "research"

    task_id = await submit_task(task_type, topic)

    return {
        "task_id": task_id,
        "status": "submitted",
        # No notification promise: delivery depends on an active WebSocket session.
        "message": (
            f"Background {task_type} started (task {task_id}). "
            "Results will be delivered to your active session when complete."
        ),
    }


register_skill(
    Skill(
        name="background_research",
        summary="Research a topic in the background",
        description=(
            "Submit a research, analysis, or summary task to run in the background. "
            "Uses web search to gather information. "
            "Results are delivered to the active session when complete — "
            "only offer this when the user has an active connection. "
            "Do not promise to 'notify' or 'let you know' — results appear in session only."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic or question to research",
                },
                "task_type": {
                    "type": "string",
                    "enum": ["research", "analysis", "summary"],
                    "description": "Type of background task (default: research)",
                },
            },
            "required": ["topic"],
        },
        handler=handle_background_research,
        timeout=10,
        # background_research uses web_search internally (_do_research calls handle_web_search);
        # only offer it when SearXNG is configured and reachable.
        enabled_check=lambda: get_settings().web_search_enabled and is_reachable("web_search"),
        unavailable_reason=lambda: (
            "SEARXNG_URL not set"
            if not get_settings().web_search_enabled
            else "SearXNG not reachable (will retry in 5 min)"
        ),
    )
)
