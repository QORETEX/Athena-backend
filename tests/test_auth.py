"""Tests for Phase 2A authentication: tokens, registration, login, refresh, logout."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.auth.tokens import (
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    make_refresh_token,
)
from app.config import get_settings
from main import PUBLIC_ROUTES, app


# ── Token unit tests ──────────────────────────────────────────────────────────


def test_create_and_decode_access_token():
    token = create_access_token(42)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["iss"] == "athena"
    for claim in ("sub", "type", "iss", "iat", "exp", "jti"):
        assert claim in payload


def test_decode_rejects_wrong_type():
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        {
            "sub": "1",
            "type": "refresh",
            "iss": "athena",
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "jti": secrets.token_hex(16),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.PyJWTError):
        decode_access_token(token)


def test_decode_rejects_missing_claims():
    settings = get_settings()
    now = datetime.now(timezone.utc)
    # Missing jti
    token = pyjwt.encode(
        {"sub": "1", "type": "access", "iss": "athena", "iat": now, "exp": now + timedelta(minutes=15)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.PyJWTError):
        decode_access_token(token)


def test_make_refresh_token_unique():
    raw1, hash1 = make_refresh_token()
    raw2, hash2 = make_refresh_token()
    assert raw1 != raw2
    assert hash1 != hash2
    assert hash_refresh_token(raw1) == hash1
    assert hash_refresh_token(raw2) == hash2


# ── PUBLIC_ROUTES coverage ────────────────────────────────────────────────────


def test_public_routes_contains_required():
    required = {
        "/health",
        "/api/auth/google",
        "/api/auth/apple",
        "/api/auth/refresh",
        "/api/auth/register",
        "/api/auth/login",
    }
    assert required.issubset(PUBLIC_ROUTES)


def test_health_is_public(client: TestClient):
    assert client.get("/health").status_code == 200


def test_notes_requires_auth(client: TestClient):
    resp = client.get("/api/notes")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_reminders_requires_auth(client: TestClient):
    assert client.get("/api/reminders").status_code == 401


def test_me_requires_auth(client: TestClient):
    assert client.get("/api/auth/me").status_code == 401


# ── Registration ──────────────────────────────────────────────────────────────


def test_register_returns_token_pair(client: TestClient):
    resp = client.post("/api/auth/register", json={
        "email": "newuser@example.com",
        "password": "securepass123",
        "name": "New User",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["name"] == "New User"


def test_register_normalizes_email(client: TestClient):
    resp = client.post("/api/auth/register", json={
        "email": "  UPPER@EXAMPLE.COM  ",
        "password": "securepass123",
    })
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "upper@example.com"


def test_register_duplicate_returns_409(client: TestClient):
    payload = {"email": "dup@example.com", "password": "securepass123"}
    assert client.post("/api/auth/register", json=payload).status_code == 200
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_register_short_password_returns_422(client: TestClient):
    resp = client.post("/api/auth/register", json={
        "email": "user@example.com",
        "password": "short",
    })
    assert resp.status_code == 422


def test_register_disabled_returns_404(client: TestClient):
    from app.config import Settings
    fake = Settings(_env_file=None, environment="development", password_auth_enabled=False)
    with patch("app.auth.password.get_settings", return_value=fake):
        resp = client.post("/api/auth/register", json={
            "email": "x@example.com",
            "password": "securepass123",
        })
    assert resp.status_code == 404


# ── Login ─────────────────────────────────────────────────────────────────────


def test_login_success(client: TestClient):
    creds = {"email": "logintest@example.com", "password": "mypassword99"}
    assert client.post("/api/auth/register", json=creds).status_code == 200

    resp = client.post("/api/auth/login", json=creds)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "logintest@example.com"


def test_login_wrong_password_returns_401(client: TestClient):
    client.post("/api/auth/register", json={"email": "wrongpw@example.com", "password": "correct_pw99"})
    resp = client.post("/api/auth/login", json={"email": "wrongpw@example.com", "password": "wrong_pw99"})
    assert resp.status_code == 401


def test_login_unknown_email_returns_401(client: TestClient):
    resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "anypass123"})
    assert resp.status_code == 401


def test_login_disabled_returns_404(client: TestClient):
    from app.config import Settings
    client.post("/api/auth/register", json={"email": "dis@example.com", "password": "securepass123"})
    fake = Settings(_env_file=None, environment="development", password_auth_enabled=False)
    with patch("app.auth.password.get_settings", return_value=fake):
        resp = client.post("/api/auth/login", json={"email": "dis@example.com", "password": "securepass123"})
    assert resp.status_code == 404


# ── /me ───────────────────────────────────────────────────────────────────────


def test_me_returns_profile(authenticated_client: TestClient):
    resp = authenticated_client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "testuser@example.com"
    assert "id" in data


def test_me_invalid_token_returns_401(client: TestClient):
    tc = TestClient(app, headers={"Authorization": "Bearer not.a.real.token"})
    assert tc.get("/api/auth/me").status_code == 401


# ── Refresh rotation ──────────────────────────────────────────────────────────


def test_refresh_issues_new_pair(client: TestClient):
    reg = client.post("/api/auth/register", json={
        "email": "refresh@example.com",
        "password": "refreshpass123",
    })
    original_rt = reg.json()["refresh_token"]

    resp = client.post("/api/auth/refresh", json={"refresh_token": original_rt})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != original_rt


def test_refresh_old_token_invalid_after_rotation(client: TestClient):
    reg = client.post("/api/auth/register", json={
        "email": "rotation@example.com",
        "password": "rotationpass123",
    })
    original_rt = reg.json()["refresh_token"]

    r1 = client.post("/api/auth/refresh", json={"refresh_token": original_rt})
    assert r1.status_code == 200

    # Old token should be rejected
    r2 = client.post("/api/auth/refresh", json={"refresh_token": original_rt})
    assert r2.status_code == 401


def test_refresh_reuse_revokes_family(client: TestClient):
    reg = client.post("/api/auth/register", json={
        "email": "reuse@example.com",
        "password": "reusepass123",
    })
    original_rt = reg.json()["refresh_token"]

    r1 = client.post("/api/auth/refresh", json={"refresh_token": original_rt})
    assert r1.status_code == 200
    new_rt = r1.json()["refresh_token"]

    # Reuse the already-revoked original — triggers family revocation
    r2 = client.post("/api/auth/refresh", json={"refresh_token": original_rt})
    assert r2.status_code == 401

    # The newly issued token is now also revoked
    r3 = client.post("/api/auth/refresh", json={"refresh_token": new_rt})
    assert r3.status_code == 401


def test_refresh_invalid_token_returns_401(client: TestClient):
    resp = client.post("/api/auth/refresh", json={"refresh_token": "totallyinvalidtoken"})
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────


def test_logout_revokes_refresh_token(client: TestClient):
    reg = client.post("/api/auth/register", json={
        "email": "logout@example.com",
        "password": "logoutpass123",
    })
    data = reg.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    auth_tc = TestClient(app, headers={"Authorization": f"Bearer {access_token}"})
    resp = auth_tc.post("/api/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 200

    # Revoked token should be rejected on refresh
    r = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 401


def test_password_auth_disabled(client: TestClient):
    """Password gate only covers /register and /login — not other protected routes."""
    from app.config import Settings
    from unittest.mock import patch
    disabled = Settings(_env_file=None, environment="development", password_auth_enabled=False)
    with patch("app.auth.password.get_settings", return_value=disabled):
        assert client.post("/api/auth/register", json={
            "email": "x@example.com", "password": "securepass123",
        }).status_code == 404
        assert client.post("/api/auth/login", json={
            "email": "x@example.com", "password": "securepass123",
        }).status_code == 404
    # /me without a token must still return 401 regardless of the password flag
    assert client.get("/api/auth/me").status_code == 401


def test_logout_all_revokes_all_sessions(client: TestClient):
    creds = {"email": "logoutall@example.com", "password": "logoutallpass123"}
    reg = client.post("/api/auth/register", json=creds)
    data = reg.json()
    access_token = data["access_token"]
    rt1 = data["refresh_token"]

    # Second session
    login = client.post("/api/auth/login", json=creds)
    rt2 = login.json()["refresh_token"]

    auth_tc = TestClient(app, headers={"Authorization": f"Bearer {access_token}"})
    resp = auth_tc.post("/api/auth/logout-all")
    assert resp.status_code == 200

    assert client.post("/api/auth/refresh", json={"refresh_token": rt1}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": rt2}).status_code == 401
