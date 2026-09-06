from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.providers import verify_apple_token, verify_google_token
from app.config import get_settings
from app.db import User, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    id_token: str
    name: str | None = None


class AuthResponse(BaseModel):
    token: str
    user: dict


class UserProfile(BaseModel):
    id: int
    provider: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    last_login: datetime


def _create_session_token(user: User) -> str:
    settings = get_settings()
    payload = {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "provider": user.provider,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_expiry_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def _upsert_user(
    db: AsyncSession, provider_info: dict, client_name: str | None = None
) -> User:
    """Find existing user or create a new one. Update last_login either way."""
    stmt = select(User).where(
        User.provider == provider_info["provider"],
        User.provider_id == provider_info["provider_id"],
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if user:
        user.last_login = now
        if provider_info.get("email") and not user.email:
            user.email = provider_info["email"]
        if provider_info.get("name") and not user.name:
            user.name = provider_info["name"]
        elif client_name and not user.name:
            user.name = client_name
        if provider_info.get("avatar_url") and not user.avatar_url:
            user.avatar_url = provider_info["avatar_url"]
    else:
        user = User(
            provider=provider_info["provider"],
            provider_id=provider_info["provider_id"],
            email=provider_info.get("email"),
            name=provider_info.get("name") or client_name,
            avatar_url=provider_info.get("avatar_url"),
            created_at=now,
            last_login=now,
        )
        db.add(user)

    await db.flush()
    await db.refresh(user)
    return user


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "provider": user.provider,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


@router.post("/google", response_model=AuthResponse)
async def login_google(body: AuthRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with a Google ID token from the mobile app."""
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google auth not configured — set GOOGLE_CLIENT_ID in .env")

    provider_info = await verify_google_token(body.id_token, settings.google_client_id)
    if "error" in provider_info:
        raise HTTPException(status_code=401, detail=provider_info["error"])

    user = await _upsert_user(db, provider_info, client_name=body.name)
    token = _create_session_token(user)

    return AuthResponse(token=token, user=_user_to_dict(user))


@router.post("/apple", response_model=AuthResponse)
async def login_apple(body: AuthRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with an Apple ID token from the mobile app."""
    settings = get_settings()
    if not settings.apple_client_id:
        raise HTTPException(status_code=503, detail="Apple auth not configured — set APPLE_CLIENT_ID in .env")

    provider_info = await verify_apple_token(body.id_token, settings.apple_client_id)
    if "error" in provider_info:
        raise HTTPException(status_code=401, detail=provider_info["error"])

    user = await _upsert_user(db, provider_info, client_name=body.name)
    token = _create_session_token(user)

    return AuthResponse(token=token, user=_user_to_dict(user))


@router.get("/me")
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current authenticated user's profile."""
    user_id = current_user.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return _user_to_dict(user)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid JWT for a fresh one with extended expiry."""
    user_id = current_user.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.last_login = datetime.now(timezone.utc)
    await db.flush()

    token = _create_session_token(user)
    return AuthResponse(token=token, user=_user_to_dict(user))
