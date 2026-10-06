"""
Device tool definitions and registration

These tools are executed on the client device (mobile app), not the backend.
The backend only passes tool calls through via SSE and receives results back.
"""
import json
import logging
from pathlib import Path

from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)

DEVICE_TOOLS_FILE = Path(__file__).parent.parent / "device-tool-definitions.json"


def load_device_tools():
    """Load device tool definitions from JSON and register them as client-executed skills"""
    if not DEVICE_TOOLS_FILE.exists():
        logger.warning(f"Device tools file not found: {DEVICE_TOOLS_FILE}")
        return

    try:
        with open(DEVICE_TOOLS_FILE, "r") as f:
            tools = json.load(f)

        for tool in tools:
            skill = Skill(
                name=tool["name"],
                description=tool["description"],
                parameters=tool["parameters"],
                handler=None,  # No handler - executed on client
                client_executed=True,  # Critical: tells backend to pass through, not execute
                timeout=30.0,
            )
            register_skill(skill)

        logger.info(f"✅ Registered {len(tools)} device tools (client-executed)")

    except Exception as e:
        logger.error(f"Failed to load device tools: {e}", exc_info=True)


def get_device_tool_names() -> set[str]:
    """Get set of all device tool names for quick lookup"""
    if not DEVICE_TOOLS_FILE.exists():
        return set()

    try:
        with open(DEVICE_TOOLS_FILE, "r") as f:
            tools = json.load(f)
        return {tool["name"] for tool in tools}
    except Exception:
        return set()
