from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import create_access_token, make_refresh_token
from app.config import get_settings
from app.db import RefreshToken, User, UserIdentity, get_db
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_ph = PasswordHasher()
# Pre-hashed dummy for constant-time comparison when user is not found.
_DUMMY_HASH = _ph.hash("dummy-timing-equalization-placeholder")


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


def _normalize(email: str) -> str:
    return email.strip().lower()


def _check_password_length(password: str) -> None:
    if not 8 <= len(password) <= 128:
        raise HTTPException(status_code=422, detail="Password must be 8–128 characters")


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "preferred_name": user.preferred_name,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def _not_found() -> HTTPException:
    # 404 makes the endpoint indistinguishable from nonexistent.
    return HTTPException(status_code=404)


@router.post("/register")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register with email/password. Returns 404 when PASSWORD_AUTH_ENABLED is false."""
    if not get_settings().password_auth_enabled:
        raise _not_found()

    email = _normalize(body.email)
    _check_password_length(body.password)

    stmt = select(User).where(User.email == email)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    pw_hash = _ph.hash(body.password)
    now = datetime.now(timezone.utc)

    user = User(
        email=email,
        name=body.name,
        password_hash=pw_hash,
        is_active=True,
        created_at=now,
        last_login=now,
    )
    db.add(user)
    await db.flush()

    db.add(UserIdentity(
        user_id=user.id,
        provider="password",
        subject=email,
        email_at_link=email,
        created_at=now,
    ))

    settings = get_settings()
    raw_refresh, refresh_hash = make_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        family_id=str(uuid.uuid4()),
        issued_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    ))
    await db.flush()

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
        "user": _user_dict(user),
    }


@router.post("/login")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login with email/password. Returns 404 when PASSWORD_AUTH_ENABLED is false."""
    if not get_settings().password_auth_enabled:
        raise _not_found()

    email = _normalize(body.email)

    stmt = select(User).where(User.email == email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    # Always verify against something to keep timing constant.
    pw_hash = (user.password_hash if user and user.password_hash else _DUMMY_HASH)

    try:
        _ph.verify(pw_hash, body.password)
        if not user or not user.password_hash:
            raise VerifyMismatchError()
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    now = datetime.now(timezone.utc)
    user.last_login = now
    await db.flush()

    settings = get_settings()
    raw_refresh, refresh_hash = make_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        family_id=str(uuid.uuid4()),
        issued_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    ))
    await db.flush()

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
        "user": _user_dict(user),
    }
