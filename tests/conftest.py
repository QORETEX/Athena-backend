"""Pytest configuration and fixtures for Athena backend tests."""
import os
from typing import AsyncGenerator

# Set test environment BEFORE any app imports so Settings() picks them up.
# Hard-set (not setdefault) so no shell variable can override these.
os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only-padded-abcdef"
os.environ["PASSWORD_AUTH_ENABLED"] = "true"
os.environ["RATE_LIMIT_AUTH"] = "10000/minute"
os.environ["RATE_LIMIT_LLM"] = "10000/minute"
os.environ["RATE_LIMIT_IMAGE"] = "10000/minute"

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import Settings, get_settings

# Clear any stale lru_cache entry from a prior import.
get_settings.cache_clear()

# Build test settings that never read .env — result is deterministic in any
# shell environment, including `env -i PATH=... HOME=... pytest ...`.
_test_settings = Settings(
    _env_file=None,
    environment="development",
    database_url="sqlite+aiosqlite:///:memory:",
    jwt_secret="test-secret-key-for-testing-only-padded-abcdef",
    password_auth_enabled=True,
    rate_limit_auth="10000/minute",
    rate_limit_llm="10000/minute",
    rate_limit_image="10000/minute",
)

# Replace the module-level get_settings so every app module imported after
# this point gets our test settings when it does `from app.config import get_settings`.
import app.config as _config
_config.get_settings = lambda: _test_settings  # type: ignore[assignment]

from app.db import Base, get_db
from app.rate_limit import limiter
from main import app

# Disable SlowAPI rate limiting in tests.
limiter._enabled = False

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh test database for each test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def override_get_db(test_db: AsyncSession):
    """Override the get_db dependency to use test database."""
    async def _override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(override_get_db) -> TestClient:
    """Create a test client with database override."""
    return TestClient(app)


@pytest.fixture
def authenticated_client(override_get_db) -> TestClient:
    """TestClient pre-authenticated with a test user via /api/auth/register."""
    tc = TestClient(app)
    resp = tc.post("/api/auth/register", json={
        "email": "testuser@example.com",
        "password": "testpassword123",
        "name": "Test User",
    })
    assert resp.status_code == 200, f"Register failed: {resp.status_code} {resp.text}"
    token = resp.json()["access_token"]
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest_asyncio.fixture
async def async_client(override_get_db) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_ollama_response():
    """Mock Ollama API response."""
    return {
        "model": "llama3.2",
        "created_at": "2026-09-06T12:00:00Z",
        "response": "This is a test response from the LLM.",
        "done": True,
        "context": [],
        "total_duration": 1000000000,
        "load_duration": 500000000,
        "prompt_eval_count": 10,
        "eval_count": 20
    }


@pytest.fixture
def mock_jwt_token():
    """Generate a mock JWT token for testing."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IlRlc3QgVXNlciIsImlhdCI6MTUxNjIzOTAyMn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"


@pytest.fixture
def sample_audio_data():
    """Sample audio data for testing (base64 encoded WAV header)."""
    return "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
