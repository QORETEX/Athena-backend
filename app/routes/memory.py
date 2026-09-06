from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.memory.store import get_memory_store

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryAdd(BaseModel):
    text: str
    long_term: bool = False
    metadata: dict = {}


@router.get("/search")
async def search_memory(q: str, top_k: int = 5, long_term: bool = False):
    """Search stored memories. Use long_term=true for persistent memories."""
    store = get_memory_store()
    if store is None or not store.available:
        return {"error": "Memory store not available (ChromaDB not installed)", "results": []}

    results = await store.search(q, top_k=top_k, long_term=long_term)
    return {"query": q, "results": results, "count": len(results)}


@router.post("/")
async def add_memory(body: MemoryAdd):
    """Store a new memory entry."""
    store = get_memory_store()
    if store is None or not store.available:
        return {"error": "Memory store not available (ChromaDB not installed)"}

    await store.add_memory(body.text, metadata=body.metadata, long_term=body.long_term)
    return {"status": "stored", "long_term": body.long_term}


@router.post("/cleanup")
async def cleanup_memory(max_age_hours: int = 24):
    """Remove short-term memories older than max_age_hours."""
    store = get_memory_store()
    if store is None or not store.available:
        return {"error": "Memory store not available"}

    await store.cleanup_short_term(max_age_hours=max_age_hours)
    return {"status": "cleaned", "max_age_hours": max_age_hours}
