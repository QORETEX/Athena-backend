"""Pattern Learning Endpoints — per-user behavior patterns."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import User, get_db
from app.services.pattern_learning import PatternLearningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


class RecordPatternRequest(BaseModel):
    pattern_type: str
    pattern_key: str
    pattern_value: str
    confidence: float = 0.5


class DetectAnomalyRequest(BaseModel):
    pattern_type: str
    pattern_key: str
    current_value: str


@router.post("/record")
async def record_pattern(
    request: RecordPatternRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PatternLearningService(db, current_user.id)
    pattern_id = await service.record_pattern(
        pattern_type=request.pattern_type,
        pattern_key=request.pattern_key,
        pattern_value=request.pattern_value,
        confidence=request.confidence,
    )
    return {"status": "ok", "pattern_id": pattern_id}


@router.get("/all")
async def get_all_patterns(
    pattern_type: str | None = Query(None, description="Filter by type"),
    min_confidence: float = Query(0.5, description="Minimum confidence"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PatternLearningService(db, current_user.id)
    patterns = await service.get_all_patterns(pattern_type, min_confidence)
    return {"patterns": patterns, "count": len(patterns)}


@router.get("/{pattern_type}/{pattern_key}")
async def get_pattern(
    pattern_type: str,
    pattern_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PatternLearningService(db, current_user.id)
    pattern = await service.get_pattern(pattern_type, pattern_key)
    if pattern is None:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern


@router.post("/detect-anomaly")
async def detect_anomaly(
    request: DetectAnomalyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PatternLearningService(db, current_user.id)
    anomaly = await service.detect_anomaly(
        pattern_type=request.pattern_type,
        pattern_key=request.pattern_key,
        current_value=request.current_value,
    )
    return anomaly or {"status": "normal", "message": "No anomaly detected"}
