from __future__ import annotations

from fastapi import APIRouter

from app.skills.web_search import handle_web_search

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/")
async def web_search(q: str):
    """Search the web via SearXNG. Requires SearXNG running locally."""
    return await handle_web_search(query=q)
