from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.db import User
from app.skills.base import skills_for

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("/")
async def list_skills(
    available: bool | None = None,
    client_capabilities: bool = False,
    current_user: User = Depends(get_current_user),
):
    """List all registered skills with availability information.

    Query parameters
    ----------------
    available : bool, optional
        When true, return only skills that are currently available.
    client_capabilities : bool, default false
        When true, treat client_executed skills as available (as the WS
        voice channel does).  Defaults to false (HTTP client, no device relay).
    """
    all_skills = skills_for(client_capabilities=client_capabilities, user=current_user)
    if available is True:
        all_skills = [s for s in all_skills if s.available]
    return [
        {
            "name": s.name,
            "summary": s.summary,
            "description": s.description,
            "parameters": s.parameters,
            "client_executed": s.client_executed,
            "available": s.available,
            "unavailable_reason": s.unavailable_reason,
        }
        for s in all_skills
    ]
