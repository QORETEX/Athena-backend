"""Phase 2B: per-user data isolation regression suite.

Each test creates a row owned by user A directly in the test database, then
verifies that user B's HTTP calls cannot list, fetch, update, or delete it,
and that A's row remains intact.

Any route prefix that is neither in COVERED nor in EXEMPT causes the coverage
check to fail, forcing new routes to be consciously categorised.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.db import (
    AutomationRule,
    BackgroundTask,
    Contact,
    ConversationLog,
    FocusSession,
    JournalEntry,
    LongTermMemory,
    Note,
    NotificationLog,
    QuickAction,
    Reminder,
    Routine,
    SmartHomeDevice,
    UserKnowledge,
    UserPattern,
    UserPreference,
)


# ── Coverage manifest ─────────────────────────────────────────────────────────

# Routes with isolation tests in this file.
COVERED: frozenset[str] = frozenset(
    {
        "/api/reminders",
        "/api/notes",
        "/api/conversations",
        "/api/notifications",
        "/api/routines",
        "/api/tasks",
        "/api/automation",
        "/api/relationships",
        "/api/focus",
        "/api/shortcuts",
        "/api/preferences",
        "/api/memory",    # covers memory_facts.py (/api/memory/facts) and memory.py
        "/api/learning",
        "/api/journal",
        "/api/smart-home",
        "/api/patterns",
        "/api/memory-enhanced",
    }
)

# Routes explicitly exempt from isolation testing, with documented reasons.
EXEMPT: dict[str, str] = {
    "/health": "public health-check endpoint; no user data",
    "/api/auth": "authentication routes; tokens are user-scoped by definition",
    "/api/skills": "skill-registry metadata; no per-user rows",
    "/api/briefing": "read-only generated content; no mutable user rows",
    "/api/chat": "LLM proxy; no persistent per-user rows created per request",
    "/api/commute": "external traffic API; no stored rows",
    "/api/context": "stateless device-context push; no persistent rows",
    "/api/image": "LLM image-generation proxy; no stored rows",
    "/api/search": "external search API; no stored rows",
    "/api/vision": "vision processing; no stored rows",
    "/api/weather": "external weather API; no stored rows",
    "/api/wellness": "external health-data aggregator; no stored rows",
    "/api/emails": "Gmail sync (OAuth); requires external credentials",
    "/api/calendar": "Google Calendar sync (OAuth); requires external credentials",
    "/api/push": "device-token management; no list endpoint to verify isolation",
    "/api/knowledge": "ChromaDB knowledge base; not available in test env",
    "/api/_test_access_log_500": "test-only route added to the app by tests/test_access_log.py; no user data",
    "/api/_test_access_log_ok": "test-only route added to the app by tests/test_access_log.py; no user data",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Isolation tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reminders_isolation(user_a, user_b, client_a, client_b, test_db):
    row = Reminder(user_id=user_a["id"], text="A's secret reminder", remind_at=_now())
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    # B's list must not include A's reminder
    resp_b = client_b.get("/api/reminders")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert row.id not in ids_b, "B can see A's reminder in list (isolation violation)"

    # B's PATCH/DELETE by ID must return 404
    assert client_b.patch(f"/api/reminders/{row.id}", json={"completed": True}).status_code == 404
    assert client_b.delete(f"/api/reminders/{row.id}").status_code == 404

    # A can still see it
    resp_a = client_a.get("/api/reminders")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's reminder disappeared"


@pytest.mark.asyncio
async def test_notes_isolation(user_a, user_b, client_a, client_b, test_db):
    row = Note(user_id=user_a["id"], content="A's private note")
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/notes")
    assert resp_b.status_code == 200
    assert row.id not in [r["id"] for r in resp_b.json()], "B can see A's note (isolation violation)"

    assert client_b.patch(f"/api/notes/{row.id}", json={"content": "hacked"}).status_code == 404
    assert client_b.delete(f"/api/notes/{row.id}").status_code == 404

    resp_a = client_a.get("/api/notes")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's note disappeared"


@pytest.mark.asyncio
async def test_conversations_isolation(user_a, user_b, client_a, client_b, test_db):
    row = ConversationLog(user_id=user_a["id"], role="user", content="A's secret message")
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/conversations/")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert row.id not in ids_b, "B can see A's conversation log (isolation violation)"

    # A can still see it
    resp_a = client_a.get("/api/conversations/")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's conversation disappeared"


@pytest.mark.asyncio
async def test_notifications_isolation(user_a, user_b, client_a, client_b, test_db):
    row = NotificationLog(
        user_id=user_a["id"],
        event_type="test",
        priority="normal",
        title="A's notification",
        read=False,
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/notifications/")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert row.id not in ids_b, "B can see A's notification (isolation violation)"

    # B marking A's notification as read must fail
    resp = client_b.post(f"/api/notifications/{row.id}/read")
    assert resp.status_code in (404, 403, 400), (
        f"B marked A's notification as read (isolation violation), status {resp.status_code}"
    )

    resp_a = client_a.get("/api/notifications/")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's notification disappeared"


@pytest.mark.asyncio
async def test_routines_isolation(user_a, user_b, client_a, client_b, test_db):
    row = Routine(
        user_id=user_a["id"],
        name="A's morning routine",
        trigger_type="time",
        trigger_config=json.dumps({"time": "07:00"}),
        actions=json.dumps([]),
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/routines/")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert row.id not in ids_b, "B can see A's routine (isolation violation)"

    assert client_b.get(f"/api/routines/{row.id}").status_code == 404
    assert client_b.patch(f"/api/routines/{row.id}", json={"name": "hacked"}).status_code == 404
    assert client_b.delete(f"/api/routines/{row.id}").status_code == 404

    resp_a = client_a.get("/api/routines/")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's routine disappeared"


@pytest.mark.asyncio
async def test_tasks_isolation(user_a, user_b, client_a, client_b, test_db):
    row = BackgroundTask(user_id=user_a["id"], task_type="research", prompt="A's task", status="pending")
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/tasks/")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert row.id not in ids_b, "B can see A's task (isolation violation)"

    assert client_b.get(f"/api/tasks/{row.id}").status_code == 404
    assert client_b.delete(f"/api/tasks/{row.id}").status_code == 404

    resp_a = client_a.get("/api/tasks/")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's task disappeared"



@pytest.mark.asyncio
async def test_automation_isolation(user_a, user_b, client_a, client_b, test_db):
    row = AutomationRule(
        user_id=user_a["id"],
        name="A's automation",
        trigger_conditions=json.dumps({"event": "morning"}),
        actions=json.dumps([{"type": "notify"}]),
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/automation/rules")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert row.id not in ids_b, "B can see A's automation rule (isolation violation)"

    assert client_b.get(f"/api/automation/rules/{row.id}").status_code == 404
    assert client_b.patch(f"/api/automation/rules/{row.id}", json={"name": "hacked"}).status_code == 404
    assert client_b.delete(f"/api/automation/rules/{row.id}").status_code == 404

    resp_a = client_a.get("/api/automation/rules")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's rule disappeared"


@pytest.mark.asyncio
async def test_relationships_isolation(user_a, user_b, client_a, client_b, test_db):
    row = Contact(
        user_id=user_a["id"],
        name="A's private contact",
        relationship="friend",
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/relationships/contacts")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert row.id not in ids_b, "B can see A's contact (isolation violation)"

    assert client_b.get(f"/api/relationships/contacts/{row.id}").status_code == 404
    assert client_b.patch(f"/api/relationships/contacts/{row.id}", json={"name": "hacked"}).status_code == 404
    assert client_b.delete(f"/api/relationships/contacts/{row.id}").status_code == 404

    resp_a = client_a.get("/api/relationships/contacts")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's contact disappeared"


@pytest.mark.asyncio
async def test_focus_isolation(user_a, user_b, client_a, client_b, test_db):
    row = FocusSession(
        user_id=user_a["id"],
        start_time=_now(),
        focus_type="deep_work",
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    # ── List isolation ─────────────────────────────────────────────────────────
    resp_b = client_b.get("/api/focus/sessions")
    assert resp_b.status_code == 200
    sessions_b = resp_b.json().get("sessions", [])
    ids_b = [r["id"] for r in sessions_b]
    assert row.id not in ids_b, "B can see A's focus session (isolation violation)"

    # ── By-ID isolation: end, notification-held, interruption ─────────────────
    # B must not be able to end A's session
    assert client_b.post(
        f"/api/focus/{row.id}/end", json={}
    ).status_code == 404, "B ended A's focus session (isolation violation)"

    # B must not be able to increment held-notification count on A's session
    assert client_b.post(
        f"/api/focus/{row.id}/notification-held"
    ).status_code == 404, "B incremented A's notification-held count (isolation violation)"

    # B must not be able to record an interruption on A's session
    assert client_b.post(
        f"/api/focus/{row.id}/interruption"
    ).status_code == 404, "B recorded interruption on A's session (isolation violation)"

    # ── A's row is unchanged and accessible ────────────────────────────────────
    resp_a = client_a.get("/api/focus/sessions")
    assert resp_a.status_code == 200
    sessions_a = resp_a.json().get("sessions", [])
    assert row.id in [r["id"] for r in sessions_a], "A's focus session disappeared"


@pytest.mark.asyncio
async def test_shortcuts_isolation(user_a, user_b, client_a, client_b, test_db):
    row = QuickAction(
        user_id=user_a["id"],
        name="A's secret shortcut",
        trigger_phrase="do the thing",
        actions=json.dumps([{"type": "speak", "text": "secret"}]),
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/shortcuts/actions")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert row.id not in ids_b, "B can see A's shortcut (isolation violation)"

    assert client_b.get(f"/api/shortcuts/actions/{row.id}").status_code == 404
    assert client_b.patch(f"/api/shortcuts/actions/{row.id}", json={"name": "hacked"}).status_code == 404
    assert client_b.delete(f"/api/shortcuts/actions/{row.id}").status_code == 404

    resp_a = client_a.get("/api/shortcuts/actions")
    assert resp_a.status_code == 200
    assert row.id in [r["id"] for r in resp_a.json()], "A's shortcut disappeared"



@pytest.mark.asyncio
async def test_preferences_isolation(user_a, user_b, client_a, client_b, test_db):
    row = UserPreference(user_id=user_a["id"], key="iso_test_theme", value="dark_secret")
    test_db.add(row)
    await test_db.commit()

    # B getting A's preference key must not return A's value
    resp_b = client_b.get("/api/preferences/iso_test_theme")
    # Either 404 (correct) or it returns something — but must not return A's value
    if resp_b.status_code == 200:
        body = resp_b.json()
        value = body.get("value") if isinstance(body, dict) else str(body)
        assert value != "dark_secret", "B can read A's preference value (isolation violation)"

    # B deleting A's preference key must not work
    del_resp = client_b.delete("/api/preferences/iso_test_theme")
    # If B could delete it, A's preference would be gone
    resp_a = client_a.get("/api/preferences/iso_test_theme")
    # A must still have it
    assert resp_a.status_code == 200, "A's preference was deleted by B (isolation violation)"
    body_a = resp_a.json()
    value_a = body_a.get("value") if isinstance(body_a, dict) else str(body_a)
    assert value_a == "dark_secret", "A's preference value was altered (isolation violation)"


@pytest.mark.asyncio
async def test_memory_facts_isolation(user_a, user_b, client_a, client_b, test_db):
    """GET /api/memory/facts uses UserKnowledge scoped to current_user — must pass."""
    row = UserKnowledge(
        user_id=user_a["id"],
        category="fact",
        key="iso_test_secret",
        value="A's secret fact",
    )
    test_db.add(row)
    await test_db.commit()

    # B's list must not include A's fact
    resp_b = client_b.get("/api/memory/facts")
    assert resp_b.status_code == 200
    keys_b = [f["key"] for f in resp_b.json()]
    assert "iso_test_secret" not in keys_b, "B can see A's memory fact (isolation violation)"

    # B trying to delete A's fact by key must not succeed
    resp_del = client_b.delete("/api/memory/facts/iso_test_secret")
    # Correct behaviour: 404
    assert resp_del.status_code == 404, (
        f"B deleted A's fact (isolation violation), status {resp_del.status_code}"
    )

    # A can still see it
    resp_a = client_a.get("/api/memory/facts")
    assert resp_a.status_code == 200
    keys_a = [f["key"] for f in resp_a.json()]
    assert "iso_test_secret" in keys_a, "A's memory fact disappeared"


@pytest.mark.asyncio
async def test_smart_home_isolation(user_a, user_b, client_a, client_b, test_db):
    from main import app
    from app.routes.smart_home import _require_smart_home

    # Patch the 503 guard so test requests reach the handlers
    app.dependency_overrides[_require_smart_home] = lambda: None
    try:
        row = SmartHomeDevice(
            user_id=user_a["id"],
            entity_id="light.a_secret",
            name="A's secret light",
            device_type="light",
        )
        test_db.add(row)
        await test_db.commit()
        await test_db.refresh(row)

        resp_b = client_b.get("/api/smart-home/devices")
        assert resp_b.status_code == 200
        ids_b = [d["id"] for d in resp_b.json()]
        assert row.id not in ids_b, "B can see A's smart home device (isolation violation)"

        assert client_b.patch(f"/api/smart-home/devices/{row.id}", json={"name": "hacked"}).status_code == 404
        assert client_b.delete(f"/api/smart-home/devices/{row.id}").status_code == 404

        resp_a = client_a.get("/api/smart-home/devices")
        assert resp_a.status_code == 200
        assert row.id in [d["id"] for d in resp_a.json()], "A's device disappeared"
    finally:
        app.dependency_overrides.pop(_require_smart_home, None)


@pytest.mark.asyncio
async def test_journal_isolation(user_a, user_b, client_a, client_b, test_db):
    row = JournalEntry(
        user_id=user_a["id"],
        content="A's private journal entry",
        mood="happy",
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    resp_b = client_b.get("/api/journal/entries")
    assert resp_b.status_code == 200
    entries_b = resp_b.json().get("entries", [])
    ids_b = [e["id"] for e in entries_b]
    assert row.id not in ids_b, "B can see A's journal entry (isolation violation)"

    assert client_b.get(f"/api/journal/{row.id}").status_code == 404

    resp_a = client_a.get("/api/journal/entries")
    assert resp_a.status_code == 200
    entries_a = resp_a.json().get("entries", [])
    assert row.id in [e["id"] for e in entries_a], "A's journal entry disappeared"


@pytest.mark.asyncio
async def test_learning_isolation(user_a, user_b, client_a, client_b, test_db):
    row = UserKnowledge(
        user_id=user_a["id"],
        category="preference",
        key="iso_learn_color",
        value="A's favourite colour",
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    # ── List isolation ─────────────────────────────────────────────────────────
    resp_b = client_b.get("/api/learning/knowledge")
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    items_b = data_b if isinstance(data_b, list) else data_b.get("knowledge", data_b.get("items", []))
    ids_b = [i.get("id") for i in items_b if isinstance(i, dict)]
    assert row.id not in ids_b, "B can see A's learning item (isolation violation)"

    # ── By-ID isolation ────────────────────────────────────────────────────────
    # B must not access A's knowledge by category/key
    assert client_b.get(
        f"/api/learning/knowledge/preference/iso_learn_color"
    ).status_code == 404, "B can GET A's knowledge by category/key (isolation violation)"

    # B must not delete A's knowledge by ID
    assert client_b.delete(f"/api/learning/knowledge/{row.id}").status_code == 404

    # ── A's row is unchanged ───────────────────────────────────────────────────
    resp_a = client_a.get("/api/learning/knowledge")
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    items_a = data_a if isinstance(data_a, list) else data_a.get("knowledge", data_a.get("items", []))
    ids_a = [i.get("id") for i in items_a if isinstance(i, dict)]
    assert row.id in ids_a, "A's learning item disappeared"

    # A can still access by category/key
    resp_a_by_key = client_a.get("/api/learning/knowledge/preference/iso_learn_color")
    assert resp_a_by_key.status_code == 200, "A cannot access their own knowledge by category/key"


@pytest.mark.asyncio
async def test_patterns_isolation(user_a, user_b, client_a, client_b, test_db):
    row = UserPattern(
        user_id=user_a["id"],
        pattern_type="iso_test_type",
        pattern_key="iso_test_key",
        pattern_value="A's secret pattern value",
        confidence=0.8,
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    # ── List isolation ─────────────────────────────────────────────────────────
    resp_b = client_b.get("/api/patterns/all")
    assert resp_b.status_code == 200
    patterns_b = resp_b.json().get("patterns", [])
    keys_b = [p.get("key") for p in patterns_b]
    assert "iso_test_key" not in keys_b, "B can see A's pattern in list (isolation violation)"

    # ── By-ID isolation: get by type+key ──────────────────────────────────────
    resp = client_b.get("/api/patterns/iso_test_type/iso_test_key")
    assert resp.status_code == 404, (
        f"B can access A's pattern by type/key (isolation violation), status {resp.status_code}"
    )

    # ── A's row is unchanged and accessible ────────────────────────────────────
    resp_a = client_a.get("/api/patterns/iso_test_type/iso_test_key")
    assert resp_a.status_code == 200, "A cannot access their own pattern"
    assert resp_a.json().get("value") == "A's secret pattern value", "A's pattern value changed"


@pytest.mark.asyncio
async def test_memory_enhanced_isolation(user_a, user_b, client_a, client_b, test_db):
    row = LongTermMemory(
        user_id=user_a["id"],
        content="A's secret long-term memory iso_ltm_unique_key",
        memory_type="fact",
        importance=0.9,
    )
    test_db.add(row)
    await test_db.commit()
    await test_db.refresh(row)

    # ── Recall isolation: B's search must not return A's memory ───────────────
    resp_b = client_b.post(
        "/api/memory-enhanced/recall",
        json={"query": "iso_ltm_unique_key", "limit": 10},
    )
    assert resp_b.status_code == 200
    memories_b = resp_b.json().get("memories", [])
    ids_b = [m["id"] for m in memories_b]
    assert row.id not in ids_b, "B can recall A's long-term memory (isolation violation)"

    # ── By-ID isolation: B deleting A's memory must return 404 ────────────────
    resp_del = client_b.delete(f"/api/memory-enhanced/{row.id}")
    assert resp_del.status_code == 404, (
        f"B deleted A's memory (isolation violation), status {resp_del.status_code}"
    )

    # ── A's row is unchanged and accessible ────────────────────────────────────
    resp_a = client_a.post(
        "/api/memory-enhanced/recall",
        json={"query": "iso_ltm_unique_key", "limit": 10},
    )
    assert resp_a.status_code == 200
    memories_a = resp_a.json().get("memories", [])
    ids_a = [m["id"] for m in memories_a]
    assert row.id in ids_a, "A's long-term memory disappeared"


# ── Route coverage check ──────────────────────────────────────────────────────


def _route_prefix(path: str) -> str:
    """Return the /api/X prefix for a path, or /segment for top-level paths."""
    parts = path.strip("/").split("/")
    if not parts:
        return "/"
    if len(parts) >= 2 and parts[0] == "api":
        return "/" + parts[0] + "/" + parts[1]
    return "/" + parts[0]


def test_all_routes_covered_or_exempt():
    """Every HTTP route prefix must be either covered by an isolation test or explicitly exempt.

    This test fails when a new route is added without being assessed for isolation.
    Add its prefix to COVERED (and write a test) or to EXEMPT (with a reason).
    """
    from main import app

    schema = app.openapi()
    all_prefixes = {_route_prefix(p) for p in schema["paths"]}

    assessed = COVERED | frozenset(EXEMPT)
    uncategorised = all_prefixes - assessed

    assert not uncategorised, (
        f"The following route prefixes have no isolation test and are not exempt.\n"
        f"Add each to COVERED (write a test) or EXEMPT (with a reason):\n"
        + "\n".join(f"  {p}" for p in sorted(uncategorised))
    )
