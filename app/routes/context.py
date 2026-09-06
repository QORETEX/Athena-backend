"""
Phone context ingestion - Mobile app sends real-time device state
This gives JARVIS full awareness of user's physical context
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/context", tags=["context"])


class LocationData(BaseModel):
    latitude: float
    longitude: float
    altitude: float | None = None
    accuracy: float | None = None
    speed: float | None = None
    heading: float | None = None


class DeviceState(BaseModel):
    battery_level: float  # 0.0 - 1.0
    is_charging: bool
    network_type: str  # "wifi", "cellular", "none"
    is_screen_on: bool
    brightness: float | None = None


class ActivityData(BaseModel):
    is_moving: bool
    step_count: int | None = None
    last_interaction_seconds_ago: int


class EnvironmentData(BaseModel):
    is_headphones_connected: bool
    ambient_light: float | None = None
    ambient_noise: float | None = None


class PhoneContext(BaseModel):
    """Complete phone context snapshot"""
    timestamp: datetime

    # Location & movement
    location: LocationData | None = None
    activity: ActivityData | None = None

    # Device state
    device: DeviceState

    # Environment
    environment: EnvironmentData | None = None

    # Upcoming calendar events (next 24h)
    calendar_events: list[dict] = []

    # Recent notifications
    recent_notifications: list[dict] = []

    # App-specific
    app_version: str | None = None
    device_model: str | None = None


@router.post("/update")
async def update_context(
    context: PhoneContext,
    db: AsyncSession = Depends(get_db)
):
    """
    Mobile app sends updated context every 30-60 seconds
    JARVIS brain uses this for proactive decisions
    """
    logger.debug(f"Received phone context: location={context.location}, battery={context.device.battery_level}")

    # TODO: Store in database for pattern learning
    # For now, just store in memory/cache for JARVIS to access

    # Store in Redis or similar for real-time access
    await _store_current_context(context)

    # Trigger immediate JARVIS analysis if critical
    if _is_critical_context(context):
        from app.autonomous.jarvis_brain import get_jarvis_brain
        brain = get_jarvis_brain()
        if brain:
            # Trigger immediate thinking cycle
            logger.info("Critical context detected - triggering immediate JARVIS analysis")
            # TODO: Add immediate analysis method

    return {"status": "ok", "received_at": datetime.now(timezone.utc).isoformat()}


@router.get("/current")
async def get_current_context():
    """
    Get the most recent phone context
    Used by JARVIS brain for decision making
    """
    context = await _get_current_context()
    return context or {"error": "No recent context available"}


# Helper functions

_current_context: PhoneContext | None = None


async def _store_current_context(context: PhoneContext):
    """Store current context in memory (TODO: use Redis)"""
    global _current_context
    _current_context = context


async def _get_current_context() -> PhoneContext | None:
    """Get stored context"""
    return _current_context


def _is_critical_context(context: PhoneContext) -> bool:
    """Detect if context requires immediate attention"""

    # Low battery not charging
    if context.device.battery_level < 0.15 and not context.device.is_charging:
        return True

    # User is moving but has meeting soon
    if context.activity and context.activity.is_moving:
        if context.calendar_events:
            # Check if meeting is soon
            return True

    # Add more critical conditions
    return False


def get_phone_context() -> PhoneContext | None:
    """Helper to get current phone context from anywhere"""
    return _current_context
