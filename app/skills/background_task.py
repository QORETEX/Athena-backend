from __future__ import annotations

import logging

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
        "message": f"I've started working on that in the background. "
        f"I'll notify you when the {task_type} is ready.",
    }


register_skill(
    Skill(
        name="background_research",
        description=(
            "Submit a research, analysis, or summary task to run in the background. "
            "Use this when the user asks you to look into something, investigate a topic, "
            "or prepare a report that requires deep research. The task runs asynchronously "
            "and the user is notified when results are ready."
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
    )
)
