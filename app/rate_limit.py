"""Shared SlowAPI limiter instance for LLM / external-API routes."""
from slowapi import Limiter
from starlette.requests import Request

from app.config import get_settings


def get_client_ip(request: Request) -> str:
    """Return the client IP used as the rate-limit key.

    When TRUST_PROXY=true (Render / behind a trusted reverse proxy), Render
    appends the real client IP as the RIGHTMOST X-Forwarded-For entry.  We
    use that so a client cannot bypass the limit by spoofing the leftmost
    entry.

    When TRUST_PROXY=false (local dev / direct connections) we ignore
    X-Forwarded-For entirely and use the transport-layer host, which is not
    client-controlled.
    """
    settings = get_settings()
    if settings.trust_proxy:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip()
    return (request.client.host if request.client else None) or "127.0.0.1"


limiter = Limiter(key_func=get_client_ip)
