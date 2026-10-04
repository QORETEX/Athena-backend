from __future__ import annotations

import logging
from typing import Optional

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# Module-level singletons — created once so PyJWKClient's built-in key cache persists
# across requests.  (The existing code was already per-module, not per-request.)
_google_jwks: Optional[PyJWKClient] = None
_apple_jwks: Optional[PyJWKClient] = None


def _get_google_jwks() -> PyJWKClient:
    global _google_jwks
    if _google_jwks is None:
        _google_jwks = PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")
    return _google_jwks


def _get_apple_jwks() -> PyJWKClient:
    global _apple_jwks
    if _apple_jwks is None:
        _apple_jwks = PyJWKClient("https://appleid.apple.com/auth/keys")
    return _apple_jwks


def _email_verified(val) -> bool:
    """Accept bool True or string 'true' (Apple sends a string per their docs)."""
    return val is True or val == "true"


def _decode_with_audience_list(
    id_token: str,
    signing_key,
    algorithms: list[str],
    audience_list: list[str],
    **kwargs,
) -> dict:
    """Try each audience in the list; return the first successful claims dict."""
    last_err: Exception | None = None
    for aud in audience_list:
        try:
            return jwt.decode(
                id_token,
                signing_key,
                algorithms=algorithms,
                audience=aud,
                **kwargs,
            )
        except jwt.PyJWTError as exc:
            last_err = exc
    raise last_err  # type: ignore[misc]


async def verify_google_token(id_token: str, client_ids: list[str]) -> dict:
    """Verify a Google ID token. Requires email_verified=True."""
    global _google_jwks
    try:
        client = _get_google_jwks()
        try:
            signing_key = client.get_signing_key_from_jwt(id_token)
        except Exception:
            # JWKS key rotation: clear and refetch once.
            _google_jwks = None
            client = _get_google_jwks()
            signing_key = client.get_signing_key_from_jwt(id_token)

        claims = _decode_with_audience_list(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience_list=client_ids,
            issuer=["accounts.google.com", "https://accounts.google.com"],
        )

        if not claims.get("email_verified"):
            return {"error": "Google account email is not verified"}

        return {
            "provider": "google",
            "provider_id": claims["sub"],
            "email": claims.get("email"),
            "name": claims.get("name"),
            "avatar_url": claims.get("picture"),
        }

    except jwt.PyJWTError as exc:
        logger.warning("Google token verification failed: %s", exc)
        return {"error": f"Invalid Google token: {exc}"}
    except Exception as exc:
        logger.error("Failed to verify Google token: %s", exc)
        return {"error": f"Could not verify Google token: {exc}"}


async def verify_apple_token(id_token: str, client_ids: list[str]) -> dict:
    """Verify an Apple identity token.

    Apple's email_verified claim is often the string "true" rather than bool
    True, and the email field may be absent on sign-ins after the first.
    """
    global _apple_jwks
    try:
        client = _get_apple_jwks()
        try:
            signing_key = client.get_signing_key_from_jwt(id_token)
        except Exception:
            _apple_jwks = None
            client = _get_apple_jwks()
            signing_key = client.get_signing_key_from_jwt(id_token)

        claims = _decode_with_audience_list(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience_list=client_ids,
            issuer="https://appleid.apple.com",
        )

        # email_verified may be absent on subsequent sign-ins (email may also be
        # absent then).  When present, reject if explicitly unverified.
        ev = claims.get("email_verified")
        if ev is not None and not _email_verified(ev):
            return {"error": "Apple account email is not verified"}

        return {
            "provider": "apple",
            "provider_id": claims["sub"],
            "email": claims.get("email"),
            "name": None,
            "avatar_url": None,
        }

    except jwt.PyJWTError as exc:
        logger.warning("Apple token verification failed: %s", exc)
        return {"error": f"Invalid Apple token: {exc}"}
    except Exception as exc:
        logger.error("Failed to verify Apple token: %s", exc)
        return {"error": f"Could not verify Apple token: {exc}"}
