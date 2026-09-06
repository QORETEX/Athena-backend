from __future__ import annotations

import logging
from typing import Optional

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

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


async def verify_google_token(id_token: str, client_id: str) -> dict:
    global _google_jwks
    try:
        client = _get_google_jwks()
        try:
            signing_key = client.get_signing_key_from_jwt(id_token)
        except Exception:
            _google_jwks = None
            client = _get_google_jwks()
            signing_key = client.get_signing_key_from_jwt(id_token)

        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=["accounts.google.com", "https://accounts.google.com"],
        )

        return {
            "provider": "google",
            "provider_id": claims["sub"],
            "email": claims.get("email"),
            "name": claims.get("name"),
            "avatar_url": claims.get("picture"),
        }

    except jwt.PyJWTError as e:
        logger.warning("Google token verification failed: %s", e)
        return {"error": f"Invalid Google token: {e}"}
    except Exception as e:
        logger.error("Failed to verify Google token: %s", e)
        return {"error": f"Could not verify Google token: {e}"}


async def verify_apple_token(id_token: str, client_id: str) -> dict:
    global _apple_jwks
    try:
        client = _get_apple_jwks()
        try:
            signing_key = client.get_signing_key_from_jwt(id_token)
        except Exception:
            _apple_jwks = None
            client = _get_apple_jwks()
            signing_key = client.get_signing_key_from_jwt(id_token)

        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer="https://appleid.apple.com",
        )

        return {
            "provider": "apple",
            "provider_id": claims["sub"],
            "email": claims.get("email"),
            "name": None,
            "avatar_url": None,
        }

    except jwt.PyJWTError as e:
        logger.warning("Apple token verification failed: %s", e)
        return {"error": f"Invalid Apple token: {e}"}
    except Exception as e:
        logger.error("Failed to verify Apple token: %s", e)
        return {"error": f"Could not verify Apple token: {e}"}
