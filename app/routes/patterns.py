"""
Pattern Learning Endpoints - User behavior patterns
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.pattern_learning import get_pattern_learning_service

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
async def record_pattern(request: RecordPatternRequest):
    """
    Record a user behavior pattern

    Types: time, preference, routine, location
    """
    pattern_service = get_pattern_learning_service()
    pattern_id = await pattern_service.record_pattern(
        pattern_type=request.pattern_type,
        pattern_key=request.pattern_key,
        pattern_value=request.pattern_value,
        confidence=request.confidence
    )
    return {"status": "ok", "pattern_id": pattern_id}


@router.get("/all")
async def get_all_patterns(
    pattern_type: str | None = Query(None, description="Filter by type"),
    min_confidence: float = Query(0.5, description="Minimum confidence")
):
    """Get all learned patterns"""
    pattern_service = get_pattern_learning_service()
    patterns = await pattern_service.get_all_patterns(pattern_type, min_confidence)
    return {"patterns": patterns, "count": len(patterns)}


@router.get("/{pattern_type}/{pattern_key}")
async def get_pattern(pattern_type: str, pattern_key: str):
    """Get a specific pattern"""
    pattern_service = get_pattern_learning_service()
    pattern = await pattern_service.get_pattern(pattern_type, pattern_key)
    return pattern or {"error": "Pattern not found"}


@router.post("/detect-anomaly")
async def detect_anomaly(request: DetectAnomalyRequest):
    """
    Detect if current behavior deviates from learned pattern

    Example: User usually leaves at 8:30, but it's 9:00 and still home
    """
    pattern_service = get_pattern_learning_service()
    anomaly = await pattern_service.detect_anomaly(
        pattern_type=request.pattern_type,
        pattern_key=request.pattern_key,
        current_value=request.current_value
    )
    return anomaly or {"status": "normal", "message": "No anomaly detected"}
