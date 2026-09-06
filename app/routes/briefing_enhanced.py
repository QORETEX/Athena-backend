"""
Enhanced Briefing Endpoints - Morning/Evening briefings
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.services.briefing import get_briefing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


@router.get("/morning")
async def get_morning_briefing():
    """
    Generate comprehensive morning briefing

    Returns JARVIS-style briefing with:
    - Today's meetings
    - Reminders
    - Weather
    - Priorities
    """
    briefing_service = get_briefing_service()
    briefing = await briefing_service.generate_morning_briefing()
    return briefing


@router.get("/evening")
async def get_evening_briefing():
    """
    Generate evening briefing

    Returns:
    - Tomorrow's schedule
    - Completed tasks today
    - Prep needed for tomorrow
    """
    briefing_service = get_briefing_service()
    briefing = await briefing_service.generate_evening_briefing()
    return briefing
