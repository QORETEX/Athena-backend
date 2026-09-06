from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import UserPreference, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


# ── Standalone helper (usable outside routes) ─────────────


async def get_user_preferences() -> dict:
    """Load all user preferences as a flat dict. Safe to call from non-route code."""
    from app.db import async_session
    if async_session is None:
        return {}
    async with async_session() as session:
        result = await session.execute(select(UserPreference))
        return {row.key: row.value for row in result.scalars().all()}


# ── Request / Response models ─────────────────────────────


class PreferenceUpdate(BaseModel):
    preferences: dict[str, str]


class PreferenceResponse(BaseModel):
    key: str
    value: str

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────


@router.get("/")
async def list_preferences(db: AsyncSession = Depends(get_db)):
    """Return all preferences as a flat key-value dict."""
    result = await db.execute(select(UserPreference))
    prefs = {row.key: row.value for row in result.scalars().all()}
    return prefs


@router.put("/")
async def update_preferences(
    body: PreferenceUpdate, db: AsyncSession = Depends(get_db)
):
    """Upsert one or more preferences. Accepts a dict of key-value pairs."""
    now = datetime.now(timezone.utc)
    updated = {}

    for key, value in body.preferences.items():
        key = key.strip().lower()
        if not key:
            continue

        result = await db.execute(
            select(UserPreference).where(UserPreference.key == key)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = str(value)
            existing.updated_at = now
        else:
            pref = UserPreference(key=key, value=str(value), updated_at=now)
            db.add(pref)

        updated[key] = str(value)

    await db.flush()
    return updated


@router.get("/{key}")
async def get_preference(key: str, db: AsyncSession = Depends(get_db)):
    """Get a single preference by key."""
    result = await db.execute(
        select(UserPreference).where(UserPreference.key == key.strip().lower())
    )
    pref = result.scalar_one_or_none()
    if not pref:
        raise HTTPException(status_code=404, detail=f"Preference '{key}' not found")
    return {"key": pref.key, "value": pref.value}


@router.delete("/{key}", status_code=204)
async def delete_preference(key: str, db: AsyncSession = Depends(get_db)):
    """Delete a single preference."""
    result = await db.execute(
        select(UserPreference).where(UserPreference.key == key.strip().lower())
    )
    pref = result.scalar_one_or_none()
    if not pref:
        raise HTTPException(status_code=404, detail=f"Preference '{key}' not found")
    await db.delete(pref)
