from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SmartHomeDevice, get_db
from app.skills.smart_home import handle_smart_home

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/smart-home", tags=["smart-home"])


# ── Request / Response models ──────────────────────────────


class DeviceAction(BaseModel):
    entity_id: str
    action: str


class DeviceCreate(BaseModel):
    entity_id: str
    name: str
    device_type: str
    room: Optional[str] = None
    icon: Optional[str] = None
    is_favorite: bool = False


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    room: Optional[str] = None
    icon: Optional[str] = None
    is_favorite: Optional[bool] = None


class DeviceResponse(BaseModel):
    id: int
    entity_id: str
    name: str
    device_type: str
    room: Optional[str] = None
    icon: Optional[str] = None
    is_favorite: bool = False

    class Config:
        from_attributes = True


# ── Control ────────────────────────────────────────────────


@router.post("/control")
async def control_device(body: DeviceAction):
    """Control a smart home device via Home Assistant."""
    return await handle_smart_home(entity_id=body.entity_id, action=body.action)


# ── Device CRUD ────────────────────────────────────────────


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    room: Optional[str] = None,
    device_type: Optional[str] = None,
    favorites_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List registered smart home devices."""
    stmt = select(SmartHomeDevice).order_by(SmartHomeDevice.name)
    if room:
        stmt = stmt.where(SmartHomeDevice.room == room)
    if device_type:
        stmt = stmt.where(SmartHomeDevice.device_type == device_type)
    if favorites_only:
        stmt = stmt.where(SmartHomeDevice.is_favorite == True)  # noqa: E712

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/devices", response_model=DeviceResponse, status_code=201)
async def add_device(body: DeviceCreate, db: AsyncSession = Depends(get_db)):
    """Register a smart home device."""
    existing = await db.execute(
        select(SmartHomeDevice).where(SmartHomeDevice.entity_id == body.entity_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Device {body.entity_id} already registered")

    device = SmartHomeDevice(
        entity_id=body.entity_id,
        name=body.name,
        device_type=body.device_type,
        room=body.room,
        icon=body.icon,
        is_favorite=body.is_favorite,
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device


@router.patch("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: int,
    body: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a registered device's metadata."""
    device = await db.get(SmartHomeDevice, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if body.name is not None:
        device.name = body.name
    if body.room is not None:
        device.room = body.room
    if body.icon is not None:
        device.icon = body.icon
    if body.is_favorite is not None:
        device.is_favorite = body.is_favorite

    await db.flush()
    await db.refresh(device)
    return device


@router.delete("/devices/{device_id}", status_code=204)
async def remove_device(device_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a registered device."""
    device = await db.get(SmartHomeDevice, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.delete(device)


# ── Home Assistant discovery ───────────────────────────────


@router.get("/discover")
async def discover_devices():
    """Query Home Assistant for all available entities. Requires HASS_TOKEN in .env."""
    settings = get_settings()
    if not settings.hass_token:
        return {"error": "Home Assistant not configured — set HASS_URL and HASS_TOKEN in .env"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.hass_url}/api/states",
                headers={"Authorization": f"Bearer {settings.hass_token}"},
            )
            resp.raise_for_status()
            states = resp.json()
    except httpx.ConnectError:
        return {"error": f"Cannot connect to Home Assistant at {settings.hass_url}"}
    except httpx.HTTPError as e:
        return {"error": f"Home Assistant request failed: {e}"}

    devices = []
    for entity in states:
        eid = entity.get("entity_id", "")
        domain = eid.split(".")[0] if "." in eid else ""
        if domain in ("light", "switch", "fan", "cover", "lock", "climate", "media_player", "scene", "script"):
            attrs = entity.get("attributes", {})
            devices.append({
                "entity_id": eid,
                "name": attrs.get("friendly_name", eid),
                "device_type": domain,
                "state": entity.get("state", "unknown"),
            })

    return {"devices": devices, "count": len(devices)}


@router.get("/rooms")
async def list_rooms(db: AsyncSession = Depends(get_db)):
    """List all rooms that have devices registered."""
    result = await db.execute(
        select(SmartHomeDevice.room)
        .where(SmartHomeDevice.room.isnot(None))
        .distinct()
    )
    rooms = [r[0] for r in result.all() if r[0]]
    return {"rooms": rooms}
