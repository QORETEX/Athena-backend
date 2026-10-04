"""User-facing API for remembered facts: list, delete one, delete all."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import User, UserKnowledge, get_db

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/facts")
async def list_my_facts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all facts Athena remembers about the authenticated user."""
    result = await db.execute(
        select(UserKnowledge)
        .where(UserKnowledge.user_id == current_user.id)
        .order_by(UserKnowledge.updated_at.desc())
    )
    facts = result.scalars().all()
    return [
        {
            "key": f.key,
            "value": f.value,
            "category": f.category,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        }
        for f in facts
    ]


@router.delete("/facts/{key}")
async def delete_my_fact(
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one remembered fact by key, scoped to the authenticated user."""
    result = await db.execute(
        select(UserKnowledge).where(
            UserKnowledge.user_id == current_user.id,
            UserKnowledge.key == key,
        )
    )
    fact = result.scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=404, detail=f"Fact '{key}' not found")
    await db.delete(fact)
    return {"deleted": key}


@router.delete("/facts")
async def delete_all_my_facts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all remembered facts for the authenticated user."""
    await db.execute(
        delete(UserKnowledge).where(UserKnowledge.user_id == current_user.id)
    )
    return {"deleted": "all"}
