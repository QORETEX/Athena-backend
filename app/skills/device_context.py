"""Device context skill — reads the latest phone context for the current user.

Reads directly from the in-memory store populated by POST /api/context/update.
No HTTP call is made; context older than DEVICE_CONTEXT_MAX_AGE_SECONDS is flagged stale.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)


async def handle_get_device_context(include_location: bool = False) -> dict:
    from app.chat.pipeline import _current_user_id
    from app.routes.context import get_user_phone_context

    user_id = _current_user_id.get(None)
    if user_id is None:
        return {"available": False}

    entry = get_user_phone_context(user_id)
    if entry is None:
        return {"available": False}

    ctx, received_at = entry
    settings = get_settings()
    age_seconds = (datetime.now(timezone.utc) - received_at).total_seconds()
    stale = age_seconds > settings.device_context_max_age_seconds

    result: dict = {
        "available": True,
        "age_seconds": round(age_seconds),
        "stale": stale,
        "device": {
            "battery_level": round(ctx.device.battery_level * 100),  # 0–100 %
            "is_charging": ctx.device.is_charging,
            "network_type": ctx.device.network_type,
            "is_screen_on": ctx.device.is_screen_on,
        },
    }

    if ctx.activity:
        result["activity"] = {
            "is_moving": ctx.activity.is_moving,
            "last_interaction_seconds_ago": ctx.activity.last_interaction_seconds_ago,
        }
        if ctx.activity.step_count is not None:
            result["activity"]["step_count"] = ctx.activity.step_count

    if ctx.environment:
        result["environment"] = {
            "is_headphones_connected": ctx.environment.is_headphones_connected,
        }

    if include_location and ctx.location:
        result["location"] = {
            "latitude": ctx.location.latitude,
            "longitude": ctx.location.longitude,
        }

    return result


register_skill(
    Skill(
        name="get_device_context",
        summary="Check device status",
        description=(
            "Get the user's current device and environment state: "
            "battery level, charging status, network type, screen state, "
            "and optionally location. "
            "Use this when the user asks about their battery, phone status, "
            "or anything that requires knowing their current device context."
        ),
        parameters={
            "type": "object",
            "properties": {
                "include_location": {
                    "type": "boolean",
                    "description": "Include GPS coordinates. Only pass true when the user explicitly asks about location.",
                },
            },
        },
        handler=handle_get_device_context,
        timeout=5,
        returns_external_content=True,
    )
)
