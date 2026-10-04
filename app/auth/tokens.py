from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings

_LEEWAY = 10  # seconds of clock-skew tolerance


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iss": "athena",
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
            "jti": secrets.token_hex(16),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict:
    """Decode and fully validate an access token. Raises jwt.PyJWTError on any failure."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        options={"require": ["sub", "type", "iss", "iat", "exp", "jti"]},
        issuer="athena",
        leeway=_LEEWAY,
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def make_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex_hash). Only the hash is stored in the DB."""
    raw = secrets.token_urlsafe(32)
    return raw, _hash(raw)


def hash_refresh_token(raw: str) -> str:
    return _hash(raw)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
