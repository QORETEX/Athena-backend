import logging

import httpx

from app.config import get_settings
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)


async def handle_smart_home(entity_id: str, action: str) -> dict:
    settings = get_settings()
    if not settings.hass_token:
        return {"success": False, "error": "Home Assistant not configured — set HASS_TOKEN in .env"}

    domain = entity_id.split(".")[0]
    url = f"{settings.hass_url}/api/services/{domain}/{action}"
    headers = {
        "Authorization": f"Bearer {settings.hass_token}",
        "Content-Type": "application/json",
    }
    payload = {"entity_id": entity_id}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return {"success": True, "entity_id": entity_id, "action": action}
            return {
                "success": False,
                "error": f"Home Assistant returned {resp.status_code}: {resp.text[:200]}",
            }
    except httpx.ConnectError:
        return {"success": False, "error": f"Cannot connect to Home Assistant at {settings.hass_url}"}
    except httpx.TimeoutException:
        return {"success": False, "error": "Home Assistant request timed out"}


register_skill(
    Skill(
        name="control_smart_device",
        description="Control a smart home device via Home Assistant. Always confirm with the user before performing physical actions like turning lights on/off, locking doors, etc.",
        parameters={
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Home Assistant entity ID (e.g., 'light.living_room', 'switch.fan')",
                },
                "action": {
                    "type": "string",
                    "enum": ["turn_on", "turn_off", "toggle"],
                    "description": "Action to perform on the device",
                },
            },
            "required": ["entity_id", "action"],
        },
        handler=handle_smart_home,
        timeout=15,
    )
)
