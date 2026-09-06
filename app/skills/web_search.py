import logging

import httpx

from app.config import get_settings
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)


async def handle_web_search(query: str) -> dict:
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.searxng_url}/search",
                params={"q": query, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError:
        return {
            "error": f"Cannot connect to SearXNG at {settings.searxng_url}. Is it running?",
            "query": query,
        }
    except httpx.HTTPError as e:
        return {"error": f"Search request failed: {e}", "query": query}

    raw_results = data.get("results", [])[:5]

    return {
        "results": [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
            }
            for r in raw_results
        ],
        "query": query,
        "total_results": len(raw_results),
    }


register_skill(
    Skill(
        name="web_search",
        description="Search the web for current information using SearXNG. Use this when the user asks about recent events, news, or anything that requires up-to-date information.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
            },
            "required": ["query"],
        },
        handler=handle_web_search,
        timeout=20,
    )
)
