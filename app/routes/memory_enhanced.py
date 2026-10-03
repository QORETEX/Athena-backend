"""Enhanced Memory Endpoints — per-user long-term semantic memory."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import User, get_db
from app.services.memory_longterm import LongTermMemoryService

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
async def remember(
    request: RememberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = LongTermMemoryService(db, current_user.id)
    memory_id = await service.remember(
        content=request.content,
        memory_type=request.memory_type,
        context=request.context,
        importance=request.importance,
    )
    return {"status": "ok", "memory_id": memory_id}


@router.post("/recall")
async def recall(
    request: RecallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = LongTermMemoryService(db, current_user.id)
    memories = await service.recall(
        query=request.query,
        memory_type=request.memory_type,
        limit=request.limit,
    )
    return {"memories": memories, "count": len(memories)}


@router.get("/conversations/search")
async def search_conversations(
    query: str = Query(..., description="Search query"),
    days_back: int = Query(30, description="Days to search back"),
    limit: int = Query(10, description="Max results"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = LongTermMemoryService(db, current_user.id)
    results = await service.search_conversations(query, days_back, limit)
    return {"results": results, "count": len(results)}


@router.get("/stats")
async def get_memory_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = LongTermMemoryService(db, current_user.id)
    stats = await service.get_memory_stats()
    return stats


@router.delete("/{memory_id}")
async def forget_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = LongTermMemoryService(db, current_user.id)
    success = await service.forget(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "ok"}
