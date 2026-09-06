from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db import BackgroundTask, get_db
from app.tasks.runner import submit_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskSubmitRequest(BaseModel):
    task_type: str = "research"
    prompt: str


class TaskSubmitResponse(BaseModel):
    task_id: int
    status: str
    message: str


class TaskDetailResponse(BaseModel):
    id: int
    task_type: str
    prompt: str
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


def _task_to_response(task: BackgroundTask) -> TaskDetailResponse:
    result_val = task.result
    if result_val:
        try:
            parsed = json.loads(result_val)
            if isinstance(parsed, dict):
                result_val = parsed.get("report") or parsed.get("analysis") or parsed.get("summary") or result_val
        except (json.JSONDecodeError, TypeError):
            pass

    return TaskDetailResponse(
        id=task.id,
        task_type=task.task_type,
        prompt=task.prompt,
        status=task.status,
        result=result_val,
        error=task.error,
        created_at=task.created_at.isoformat() if task.created_at else "",
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


@router.post("/", response_model=TaskSubmitResponse, status_code=201)
async def create_task(body: TaskSubmitRequest):
    if body.task_type not in ("research", "analysis", "summary"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_type '{body.task_type}'. Must be: research, analysis, summary",
        )

    task_id = await submit_task(body.task_type, body.prompt)

    return TaskSubmitResponse(
        task_id=task_id,
        status="pending",
        message=f"Task submitted. I'll have your {body.task_type} ready shortly.",
    )


@router.get("/", response_model=list[TaskDetailResponse])
async def list_tasks(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BackgroundTask).order_by(BackgroundTask.created_at.desc())
    if status:
        stmt = stmt.where(BackgroundTask.status == status)

    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [_task_to_response(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(BackgroundTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(BackgroundTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running task")
    await db.delete(task)
