"""Shared SlowAPI limiter instance for all routes."""
from slowapi import Limiter
from starlette.requests import Request

from app.config import get_settings


def get_client_ip(request: Request) -> str:
    """Return the transport-layer client IP (no XFF considered)."""
    settings = get_settings()
    if settings.trust_proxy:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip()
    return (request.client.host if request.client else None) or "127.0.0.1"


def get_rate_limit_key(request: Request) -> str:
    """Rate-limit key: user ID for authenticated requests, IP address otherwise.

    Decodes the Bearer token without a DB hit so authenticated users are not
    limited by shared IP (e.g. behind a NAT or VPN).
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            from app.auth.tokens import decode_access_token
            payload = decode_access_token(auth[7:])
            return f"user:{payload['sub']}"
        except Exception:
            pass
    return get_client_ip(request)


limiter = Limiter(key_func=get_rate_limit_key)
