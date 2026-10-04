"""
Enhanced Briefing Endpoints - Morning/Evening briefings
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.config import get_settings
from app.rate_limit import limiter
from app.services.briefing import get_briefing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


@router.get("/morning")
@limiter.limit(get_settings().rate_limit_llm)
async def get_morning_briefing(request: Request):
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
@limiter.limit(get_settings().rate_limit_llm)
async def get_evening_briefing(request: Request):
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
