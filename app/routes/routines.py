from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Routine, get_db
from app.routines.engine import (
    execute_routine,
    register_routine,
    unregister_routine,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/routines", tags=["routines"])


# ── Request / Response models ──────────────────────────────


class ActionConfig(BaseModel):
    type: str
    config: dict = {}


class TriggerConfig(BaseModel):
    hour: Optional[str] = "*"
    minute: Optional[int] = 0
    days_of_week: Optional[str] = "*"
    event_name: Optional[str] = None


class RoutineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_type: str
    trigger_config: TriggerConfig = TriggerConfig()
    actions: list[ActionConfig] = []
    enabled: bool = True


class RoutineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[TriggerConfig] = None
    actions: Optional[list[ActionConfig]] = None
    enabled: Optional[bool] = None


class RoutineResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    trigger_type: str
    trigger_config: dict
    actions: list[dict]
    enabled: bool
    last_triggered: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


def _routine_to_response(routine: Routine) -> RoutineResponse:
    try:
        trigger_config = json.loads(routine.trigger_config)
    except (json.JSONDecodeError, TypeError):
        trigger_config = {}

    try:
        actions = json.loads(routine.actions)
    except (json.JSONDecodeError, TypeError):
        actions = []

    return RoutineResponse(
        id=routine.id,
        name=routine.name,
        description=routine.description,
        trigger_type=routine.trigger_type,
        trigger_config=trigger_config,
        actions=actions,
        enabled=routine.enabled,
        last_triggered=routine.last_triggered,
        created_at=routine.created_at,
    )


# ── Endpoints ──────────────────────────────────────────────


@router.get("/", response_model=list[RoutineResponse])
async def list_routines(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Routine).order_by(Routine.name)
    if enabled_only:
        stmt = stmt.where(Routine.enabled == True)  # noqa: E712
    result = await db.execute(stmt)
    return [_routine_to_response(r) for r in result.scalars().all()]


@router.post("/", response_model=RoutineResponse, status_code=201)
async def create_routine(body: RoutineCreate, db: AsyncSession = Depends(get_db)):
    routine = Routine(
        name=body.name,
        description=body.description,
        trigger_type=body.trigger_type,
        trigger_config=body.trigger_config.json(),
        actions=json.dumps([a.dict() for a in body.actions]),
        enabled=body.enabled,
    )
    db.add(routine)
    await db.flush()
    await db.refresh(routine)

    if routine.enabled:
        register_routine(routine.id, routine.name, routine.trigger_type, routine.trigger_config)

    return _routine_to_response(routine)


@router.get("/{routine_id}", response_model=RoutineResponse)
async def get_routine(routine_id: int, db: AsyncSession = Depends(get_db)):
    routine = await db.get(Routine, routine_id)
    if not routine:
        raise HTTPException(status_code=404, detail="Routine not found")
    return _routine_to_response(routine)


@router.patch("/{routine_id}", response_model=RoutineResponse)
async def update_routine(
    routine_id: int,
    body: RoutineUpdate,
    db: AsyncSession = Depends(get_db),
):
    routine = await db.get(Routine, routine_id)
    if not routine:
        raise HTTPException(status_code=404, detail="Routine not found")

    if body.name is not None:
        routine.name = body.name
    if body.description is not None:
        routine.description = body.description
    if body.trigger_type is not None:
        routine.trigger_type = body.trigger_type
    if body.trigger_config is not None:
        routine.trigger_config = body.trigger_config.json()
    if body.actions is not None:
        routine.actions = json.dumps([a.dict() for a in body.actions])
    if body.enabled is not None:
        routine.enabled = body.enabled

    await db.flush()
    await db.refresh(routine)

    unregister_routine(routine_id)
    if routine.enabled:
        register_routine(routine.id, routine.name, routine.trigger_type, routine.trigger_config)

    return _routine_to_response(routine)


@router.delete("/{routine_id}", status_code=204)
async def delete_routine(routine_id: int, db: AsyncSession = Depends(get_db)):
    routine = await db.get(Routine, routine_id)
    if not routine:
        raise HTTPException(status_code=404, detail="Routine not found")
    unregister_routine(routine_id)
    await db.delete(routine)


@router.post("/{routine_id}/trigger")
async def trigger_routine(routine_id: int, db: AsyncSession = Depends(get_db)):
    """Manually trigger a routine regardless of its schedule."""
    routine = await db.get(Routine, routine_id)
    if not routine:
        raise HTTPException(status_code=404, detail="Routine not found")

    result = await execute_routine(routine_id)
    return result
