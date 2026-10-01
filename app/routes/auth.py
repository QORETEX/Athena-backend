from __future__ import annotations

import logging
import uuid
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.providers import verify_apple_token, verify_google_token
from app.auth.tokens import create_access_token, hash_refresh_token, make_refresh_token
from app.config import get_settings
from app.db import RefreshToken, User, UserIdentity, get_db
from app.rate_limit import limiter

logger = logging.getLogger(__name__)


def _utc(dt: datetime) -> datetime:
    """Return dt as an aware UTC datetime (SQLite strips tzinfo on read-back)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# Public endpoints (no auth required — mounted without get_current_user in main.py).
public_router = APIRouter(prefix="/api/auth", tags=["auth"])

# Protected endpoints (mounted with get_current_user dependency in main.py).
protected_router = APIRouter(prefix="/api/auth", tags=["auth"])


class OAuthRequest(BaseModel):
    id_token: str
    name: str | None = None
    timezone: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateMeRequest(BaseModel):
    preferred_name: str | None = None
    timezone: str | None = None


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "preferred_name": user.preferred_name,
        "timezone": user.timezone,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


async def _find_or_create_oauth_user(
    db: AsyncSession,
    provider: str,
    subject: str,
    email: str | None,
    name: str | None = None,
    avatar_url: str | None = None,
    timezone_name: str | None = None,
) -> User:
    """Look up user by OAuth identity; create or link as needed.

    Raises 409 when the email belongs to an account that has only a password identity.
    """
    now = datetime.now(timezone.utc)
    if timezone_name is not None:
        try:
            ZoneInfo(timezone_name)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid IANA timezone")

    stmt = select(UserIdentity).where(
        UserIdentity.provider == provider,
        UserIdentity.subject == subject,
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()

    if identity:
        user = await db.get(User, identity.user_id)
        user.last_login = now
        if email and not user.email:
            user.email = email
        if name and not user.name:
            user.name = name
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        await db.flush()
        return user

    # No identity found — check for email collision.
    if email:
        stmt = select(User).where(User.email == email)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            stmt = select(UserIdentity).where(UserIdentity.user_id == existing.id)
            identities = (await db.execute(stmt)).scalars().all()
            providers = {i.provider for i in identities}

            if providers == {"password"}:
                raise HTTPException(
                    status_code=409,
                    detail="An account with this email exists via password login",
                )
            # Existing verified-email OAuth account → add new identity.
            db.add(UserIdentity(
                user_id=existing.id,
                provider=provider,
                subject=subject,
                email_at_link=email,
                created_at=now,
            ))
            existing.last_login = now
            await db.flush()
            return existing

    # Create a new user and identity.
    user = User(
        email=email,
        name=name,
        avatar_url=avatar_url,
        is_active=True,
        created_at=now,
        last_login=now,
        timezone=timezone_name or "UTC",
    )
    db.add(user)
    await db.flush()

    db.add(UserIdentity(
        user_id=user.id,
        provider=provider,
        subject=subject,
        email_at_link=email,
        created_at=now,
    ))
    await db.flush()
    return user


async def _issue_tokens(db: AsyncSession, user: User, user_agent: str | None) -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    raw_refresh, refresh_hash = make_refresh_token()

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        family_id=str(uuid.uuid4()),
        issued_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(user_agent or "")[:512] or None,
    ))
    await db.flush()

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
        "user": _user_dict(user),
    }


# ── Public endpoints ──────────────────────────────────────────────────────────

@public_router.post("/google")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def login_google(
    request: Request,
    body: OAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with a Google ID token."""
    settings = get_settings()
    ids = settings.google_client_id_list
    if not ids:
        raise HTTPException(status_code=503, detail="Google auth not configured — set GOOGLE_CLIENT_ID")

    info = await verify_google_token(body.id_token, ids)
    if "error" in info:
        raise HTTPException(status_code=401, detail=info["error"])

    user = await _find_or_create_oauth_user(
        db, "google", info["provider_id"], info.get("email"),
        name=body.name or info.get("name"),
        avatar_url=info.get("avatar_url"),
        timezone_name=body.timezone,
    )
    if body.timezone:
        user.timezone = body.timezone
    return await _issue_tokens(db, user, request.headers.get("user-agent"))


@public_router.post("/apple")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def login_apple(
    request: Request,
    body: OAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with an Apple identity token."""
    settings = get_settings()
    ids = settings.apple_client_id_list
    if not ids:
        raise HTTPException(status_code=503, detail="Apple auth not configured — set APPLE_CLIENT_ID")

    info = await verify_apple_token(body.id_token, ids)
    if "error" in info:
        raise HTTPException(status_code=401, detail=info["error"])

    user = await _find_or_create_oauth_user(
        db, "apple", info["provider_id"], info.get("email"),
        name=body.name,
        timezone_name=body.timezone,
    )
    if body.timezone:
        user.timezone = body.timezone
    return await _issue_tokens(db, user, request.headers.get("user-agent"))


@public_router.post("/refresh")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rotate a refresh token.  Reuse of a revoked token revokes the entire family."""
    token_hash = hash_refresh_token(body.refresh_token)

    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    stored = (await db.execute(stmt)).scalar_one_or_none()

    if stored is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    now = datetime.now(timezone.utc)

    # Reuse detection: if already revoked, kill the whole family.
    if stored.revoked_at is not None:
        stmt = select(RefreshToken).where(
            RefreshToken.family_id == stored.family_id,
            RefreshToken.revoked_at.is_(None),
        )
        active_in_family = (await db.execute(stmt)).scalars().all()
        for t in active_in_family:
            t.revoked_at = now
        await db.flush()
        raise HTTPException(status_code=401, detail="Refresh token already used — all sessions revoked")

    if _utc(stored.expires_at) < now:
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    settings = get_settings()
    raw_new, new_hash = make_refresh_token()
    new_token = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        family_id=stored.family_id,
        issued_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    )
    db.add(new_token)
    await db.flush()

    stored.revoked_at = now
    stored.replaced_by_id = new_token.id
    user.last_login = now
    await db.flush()

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": raw_new,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
        "user": _user_dict(user),
    }


# ── Protected endpoints ───────────────────────────────────────────────────────

@protected_router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return _user_dict(current_user)


@protected_router.patch("/me")
async def update_me(
    body: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update editable profile fields for the authenticated user."""
    if body.preferred_name is not None:
        stripped = body.preferred_name.strip()
        current_user.preferred_name = stripped if stripped else None
    if body.timezone is not None:
        try:
            ZoneInfo(body.timezone)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid IANA timezone")
        current_user.timezone = body.timezone
    await db.flush()
    return _user_dict(current_user)


@protected_router.post("/logout")
async def logout(
    body: RefreshRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the presented refresh token."""
    token_hash = hash_refresh_token(body.refresh_token)
    stmt = select(RefreshToken).where(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == current_user.id,
    )
    stored = (await db.execute(stmt)).scalar_one_or_none()
    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        await db.flush()
    return {"detail": "Logged out"}


@protected_router.post("/logout-all")
async def logout_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all active refresh tokens for this user."""
    now = datetime.now(timezone.utc)
    stmt = select(RefreshToken).where(
        RefreshToken.user_id == current_user.id,
        RefreshToken.revoked_at.is_(None),
    )
    tokens = (await db.execute(stmt)).scalars().all()
    for t in tokens:
        t.revoked_at = now
    await db.flush()
    return {"detail": "All sessions revoked"}
