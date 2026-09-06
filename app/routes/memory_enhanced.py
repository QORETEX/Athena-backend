"""
Enhanced Memory Endpoints - Long-term semantic memory
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.memory_longterm import get_longterm_memory_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory-enhanced", tags=["memory-enhanced"])


class RememberRequest(BaseModel):
    content: str
    memory_type: str = "conversation"
    context: str | None = None
    importance: float = 0.5


class RecallRequest(BaseModel):
    query: str
    memory_type: str | None = None
    limit: int = 5


@router.post("/remember")
async def remember(request: RememberRequest):
    """
    Store a long-term memory

    Types: conversation, fact, preference, event
    """
    memory_service = get_longterm_memory_service()
    memory_id = await memory_service.remember(
        content=request.content,
        memory_type=request.memory_type,
        context=request.context,
        importance=request.importance
    )
    return {"status": "ok", "memory_id": memory_id}


@router.post("/recall")
async def recall(request: RecallRequest):
    """
    Search long-term memories

    Example: "What did I say about the Johnson project?"
    """
    memory_service = get_longterm_memory_service()
    memories = await memory_service.recall(
        query=request.query,
        memory_type=request.memory_type,
        limit=request.limit
    )
    return {"memories": memories, "count": len(memories)}


@router.get("/conversations/search")
async def search_conversations(
    query: str = Query(..., description="Search query"),
    days_back: int = Query(30, description="Days to search back"),
    limit: int = Query(10, description="Max results")
):
    """
    Search past conversations

    Enables: "What did I tell you last week about the meeting?"
    """
    memory_service = get_longterm_memory_service()
    results = await memory_service.search_conversations(query, days_back, limit)
    return {"results": results, "count": len(results)}


@router.get("/stats")
async def get_memory_stats():
    """Get memory statistics"""
    memory_service = get_longterm_memory_service()
    stats = await memory_service.get_memory_stats()
    return stats


@router.delete("/{memory_id}")
async def forget_memory(memory_id: int):
    """Delete a specific memory"""
    memory_service = get_longterm_memory_service()
    success = await memory_service.forget(memory_id)
    return {"status": "ok" if success else "not_found"}
