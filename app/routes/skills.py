from __future__ import annotations

from fastapi import APIRouter

from app.skills.base import get_all_skills

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("/")
async def list_skills():
    skills = get_all_skills()
    return [
        {
            "name": s.name,
            "description": s.description,
            "parameters": s.parameters,
            "client_executed": s.client_executed,
        }
        for s in skills.values()
    ]
