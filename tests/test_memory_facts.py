"""Tests for per-user persistent memory: skill handlers, prompt injection, and API."""
from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.db as _appdb
from app.db import Base, User, UserKnowledge, get_db
from main import app


# ── Shared test database fixture ─────────────────────────────────────────────
#
# Uses StaticPool so all sessions in the same test share one SQLite connection
# (and therefore the same in-memory database).  Patches app.db.async_session so
# skill handlers — which bypass get_db and call async_session() directly — also
# hit the same database.  Also overrides the get_db FastAPI dependency so route
# handlers commit to the same store.


@pytest_asyncio.fixture
async def memory_env() -> AsyncGenerator[async_sessionmaker, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sess_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    old_factory = _appdb.async_session
    _appdb.async_session = sess_factory

    async def _override_get_db():
        async with sess_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    yield sess_factory

    app.dependency_overrides.clear()
    _appdb.async_session = old_factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def user_a(memory_env) -> User:
    """Create and return a test user (user A)."""
    now = datetime.now(timezone.utc)
    user = User(
        email="usera@test.com",
        name="User A",
        is_active=True,
        created_at=now,
        last_login=now,
    )
    async with memory_env() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_b(memory_env) -> User:
    now = datetime.now(timezone.utc)
    user = User(
        email="userb@test.com",
        name="User B",
        is_active=True,
        created_at=now,
        last_login=now,
    )
    async with memory_env() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.fixture
def auth_client_a(memory_env) -> TestClient:
    """TestClient authenticated as user A (registered fresh in the memory_env DB)."""
    tc = TestClient(app)
    resp = tc.post("/api/auth/register", json={
        "email": "usera_api@test.com",
        "password": "testpass123",
        "name": "Manfred",
    })
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    token = resp.json()["access_token"]
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def auth_client_b(memory_env) -> TestClient:
    """TestClient authenticated as user B."""
    tc = TestClient(app)
    resp = tc.post("/api/auth/register", json={
        "email": "userb_api@test.com",
        "password": "testpass456",
        "name": "Other User",
    })
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    token = resp.json()["access_token"]
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


# ── Skill handler tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remember_fact_stores_and_returns(memory_env, user_a):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        result = await handle_remember_fact(
            key="study_program", value="IT at KNUST", category="fact"
        )
    finally:
        _current_user_id.reset(token)

    assert result["success"] is True
    assert result["key"] == "study_program"
    assert result["value"] == "IT at KNUST"

    async with memory_env() as session:
        from sqlalchemy import select
        row = (await session.execute(
            select(UserKnowledge).where(
                UserKnowledge.user_id == user_a.id,
                UserKnowledge.key == "study_program",
            )
        )).scalar_one()
    assert row.value == "IT at KNUST"
    assert row.category == "fact"


@pytest.mark.asyncio
async def test_remember_fact_updates_existing(memory_env, user_a):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        await handle_remember_fact(key="city", value="Accra")
        result = await handle_remember_fact(key="city", value="Kumasi")
    finally:
        _current_user_id.reset(token)

    assert result["success"] is True
    assert result["value"] == "Kumasi"

    async with memory_env() as session:
        from sqlalchemy import select, func
        count = (await session.execute(
            select(func.count(UserKnowledge.id)).where(
                UserKnowledge.user_id == user_a.id,
                UserKnowledge.key == "city",
            )
        )).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_remember_fact_rejects_password_key(memory_env, user_a):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        result = await handle_remember_fact(key="password", value="hunter2")
    finally:
        _current_user_id.reset(token)

    assert result["success"] is False
    assert "sensitive" in result["error"].lower() or "credential" in result["error"].lower()


@pytest.mark.asyncio
async def test_remember_fact_rejects_card_number_value(memory_env, user_a):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        result = await handle_remember_fact(key="payment", value="4111 1111 1111 1111")
    finally:
        _current_user_id.reset(token)

    assert result["success"] is False
    assert "card" in result["error"].lower()


@pytest.mark.asyncio
async def test_forget_fact_removes_entry(memory_env, user_a):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_forget_fact, handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        await handle_remember_fact(key="hobby", value="cycling")
        result = await handle_forget_fact(key="hobby")
    finally:
        _current_user_id.reset(token)

    assert result["success"] is True

    async with memory_env() as session:
        from sqlalchemy import select
        row = (await session.execute(
            select(UserKnowledge).where(
                UserKnowledge.user_id == user_a.id,
                UserKnowledge.key == "hobby",
            )
        )).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_forget_fact_unknown_key_returns_error(memory_env, user_a):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_forget_fact

    token = _current_user_id.set(user_a.id)
    try:
        result = await handle_forget_fact(key="nonexistent_key_xyz")
    finally:
        _current_user_id.reset(token)

    assert result["success"] is False


@pytest.mark.asyncio
async def test_forget_all_facts(memory_env, user_a):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_forget_all_facts, handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        await handle_remember_fact(key="k1", value="v1")
        await handle_remember_fact(key="k2", value="v2")
        result = await handle_forget_all_facts()
    finally:
        _current_user_id.reset(token)

    assert result["success"] is True

    async with memory_env() as session:
        from sqlalchemy import select, func
        count = (await session.execute(
            select(func.count(UserKnowledge.id)).where(
                UserKnowledge.user_id == user_a.id
            )
        )).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_list_facts(memory_env, user_a):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_list_facts, handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        await handle_remember_fact(key="name", value="Manfred")
        await handle_remember_fact(key="study_program", value="IT at KNUST")
        result = await handle_list_facts()
    finally:
        _current_user_id.reset(token)

    keys = {f["key"] for f in result["facts"]}
    assert "name" in keys
    assert "study_program" in keys


# ── User isolation ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_a_cannot_see_user_b_facts(memory_env, user_a, user_b):
    from app.chat.pipeline import _current_user_id
    from app.skills.memory_facts import handle_list_facts, handle_remember_fact

    tok_b = _current_user_id.set(user_b.id)
    try:
        await handle_remember_fact(key="secret_of_b", value="only B knows this")
    finally:
        _current_user_id.reset(tok_b)

    tok_a = _current_user_id.set(user_a.id)
    try:
        result = await handle_list_facts()
    finally:
        _current_user_id.reset(tok_a)

    keys = {f["key"] for f in result["facts"]}
    assert "secret_of_b" not in keys


# ── Prompt injection ──────────────────────────────────────────────────────────


def test_profile_name_appears_in_prompt():
    from app.llm import build_system_prompt

    prompt = build_system_prompt(user_name="Manfred", user_facts=[])
    assert "Manfred" in prompt


def test_user_facts_appear_in_prompt():
    from app.llm import build_system_prompt

    facts = [
        {"key": "study_program", "value": "IT at KNUST", "category": "fact"},
        {"key": "city", "value": "Kumasi", "category": "preference"},
    ]
    prompt = build_system_prompt(user_name="Manfred", user_facts=facts, facts_available=True)
    assert "study_program" in prompt
    assert "IT at KNUST" in prompt
    assert "city" in prompt
    assert "Kumasi" in prompt


def test_no_user_block_when_no_name_and_no_facts():
    from app.llm import build_system_prompt

    prompt = build_system_prompt()
    assert "About this user" not in prompt


def test_facts_available_honesty_line():
    from app.llm import build_system_prompt

    prompt = build_system_prompt(memory_available=False, facts_available=True)
    assert "remember_fact" in prompt
    assert "Noted, I'll remember that" in prompt
    assert "Long-term memory is not available" not in prompt


def test_memory_unavailable_disclaimer_preserved_when_no_facts():
    """Old disclaimer must still appear when facts_available=False and memory_available=False."""
    from app.llm import build_system_prompt

    prompt = build_system_prompt(memory_available=False, facts_available=False)
    assert "Long-term memory is not available" in prompt


@pytest.mark.asyncio
async def test_facts_persist_across_conversations(memory_env, user_a):
    """Storing a fact and then loading user_context (simulating a fresh conversation) returns it."""
    from app.chat.pipeline import _current_user_id, _load_user_context
    from app.skills.memory_facts import handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        await handle_remember_fact(key="name", value="Manfred", category="fact")
        await handle_remember_fact(key="study_program", value="IT at KNUST", category="fact")
    finally:
        _current_user_id.reset(token)

    # Simulate a fresh conversation: load user context with no conversation history
    display_name, facts = await _load_user_context(user_a.id)
    fact_keys = {f["key"] for f in facts}

    assert "name" in fact_keys
    assert "study_program" in fact_keys
    assert any(f["value"] == "IT at KNUST" for f in facts)


@pytest.mark.asyncio
async def test_forget_fact_removes_from_next_prompt(memory_env, user_a):
    """After forget_fact, loading user context no longer includes the forgotten fact."""
    from app.chat.pipeline import _current_user_id, _load_user_context
    from app.skills.memory_facts import handle_forget_fact, handle_remember_fact

    token = _current_user_id.set(user_a.id)
    try:
        await handle_remember_fact(key="study_program", value="IT at KNUST")
        await handle_forget_fact(key="study_program")
    finally:
        _current_user_id.reset(token)

    _, facts = await _load_user_context(user_a.id)
    fact_keys = {f["key"] for f in facts}
    assert "study_program" not in fact_keys


@pytest.mark.asyncio
async def test_preferred_name_shown_in_context(memory_env):
    """preferred_name takes priority over name in _load_user_context."""
    from app.chat.pipeline import _load_user_context

    now = datetime.now(timezone.utc)
    user = User(
        email="pref@test.com",
        name="Legal Name",
        preferred_name="Manfred",
        is_active=True,
        created_at=now,
        last_login=now,
    )
    async with memory_env() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    display_name, _ = await _load_user_context(user.id)
    assert display_name == "Manfred"


# ── API endpoint tests ────────────────────────────────────────────────────────


def test_list_facts_api_requires_auth(memory_env):
    tc = TestClient(app)
    assert tc.get("/api/memory/facts").status_code == 401


def test_list_facts_api_empty(auth_client_a):
    resp = auth_client_a.get("/api/memory/facts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_facts_api_returns_stored_facts(auth_client_a, memory_env):
    """Store facts via the skill then list them via the API."""
    # We need the user_id to set the ContextVar; extract it from the /me endpoint
    me = auth_client_a.get("/api/auth/me").json()
    user_id = me["id"]

    now = datetime.now(timezone.utc)
    import asyncio

    async def _insert():
        async with memory_env() as session:
            session.add(UserKnowledge(
                user_id=user_id,
                category="fact",
                key="study_program",
                value="IT at KNUST",
                source="user",
                confidence=1.0,
                verified=True,
                related_knowledge="[]",
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_insert())

    resp = auth_client_a.get("/api/memory/facts")
    assert resp.status_code == 200
    data = resp.json()
    assert any(f["key"] == "study_program" and f["value"] == "IT at KNUST" for f in data)


def test_delete_fact_api(auth_client_a, memory_env):
    me = auth_client_a.get("/api/auth/me").json()
    user_id = me["id"]

    now = datetime.now(timezone.utc)
    import asyncio

    async def _insert():
        async with memory_env() as session:
            session.add(UserKnowledge(
                user_id=user_id,
                category="fact",
                key="city",
                value="Kumasi",
                source="user",
                confidence=1.0,
                verified=True,
                related_knowledge="[]",
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_insert())

    # Verify it's there
    assert any(f["key"] == "city" for f in auth_client_a.get("/api/memory/facts").json())

    # Delete it
    resp = auth_client_a.delete("/api/memory/facts/city")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == "city"

    # Verify it's gone
    assert not any(f["key"] == "city" for f in auth_client_a.get("/api/memory/facts").json())


def test_delete_nonexistent_fact_returns_404(auth_client_a):
    resp = auth_client_a.delete("/api/memory/facts/definitely_not_there")
    assert resp.status_code == 404


def test_delete_all_facts_api(auth_client_a, memory_env):
    me = auth_client_a.get("/api/auth/me").json()
    user_id = me["id"]

    now = datetime.now(timezone.utc)
    import asyncio

    async def _insert():
        async with memory_env() as session:
            for k in ("k1", "k2", "k3"):
                session.add(UserKnowledge(
                    user_id=user_id, category="fact", key=k, value="v",
                    source="user", confidence=1.0, verified=True,
                    related_knowledge="[]", created_at=now, updated_at=now,
                ))
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_insert())

    resp = auth_client_a.delete("/api/memory/facts")
    assert resp.status_code == 200

    assert auth_client_a.get("/api/memory/facts").json() == []


def test_user_isolation_via_api(auth_client_a, auth_client_b, memory_env):
    """User B's facts must not appear in user A's list."""
    me_b = auth_client_b.get("/api/auth/me").json()
    user_id_b = me_b["id"]

    now = datetime.now(timezone.utc)
    import asyncio

    async def _insert():
        async with memory_env() as session:
            session.add(UserKnowledge(
                user_id=user_id_b, category="fact", key="secret_b", value="only_b",
                source="user", confidence=1.0, verified=True,
                related_knowledge="[]", created_at=now, updated_at=now,
            ))
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_insert())

    # User A must not see user B's fact
    facts_a = auth_client_a.get("/api/memory/facts").json()
    assert not any(f["key"] == "secret_b" for f in facts_a)

    # User B sees their own fact
    facts_b = auth_client_b.get("/api/memory/facts").json()
    assert any(f["key"] == "secret_b" for f in facts_b)


def test_patch_me_preferred_name(auth_client_a):
    """PATCH /api/auth/me updates preferred_name and GET /api/auth/me reflects it."""
    resp = auth_client_a.patch("/api/auth/me", json={"preferred_name": "Manfred"})
    assert resp.status_code == 200
    assert resp.json()["preferred_name"] == "Manfred"

    me = auth_client_a.get("/api/auth/me").json()
    assert me["preferred_name"] == "Manfred"


def test_patch_me_clear_preferred_name(auth_client_a):
    auth_client_a.patch("/api/auth/me", json={"preferred_name": "Manfred"})
    resp = auth_client_a.patch("/api/auth/me", json={"preferred_name": ""})
    assert resp.status_code == 200
    assert resp.json()["preferred_name"] is None
