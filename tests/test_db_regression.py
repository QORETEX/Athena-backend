"""
Regression tests for the async_session=None crash (2026-09-29).

Root cause: app/db.py initialised engine and async_session as None at module
level and reassigned them inside init_db().  Modules that did
  from app.db import async_session
at their own module level captured None permanently, so every
  async with async_session() as session:
call crashed with TypeError: 'NoneType' object is not callable.

Fix: _build_engine_and_session() is called at db.py module-import time.
All bindings immediately capture a live factory.
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest

import app


def test_all_app_modules_import_without_raising():
    """No module under app/ may crash on import (ImportError for missing optional
    dependencies is acceptable; any other exception is a bug)."""
    bad: list[str] = []
    for _finder, name, _ispkg in pkgutil.walk_packages(
        path=app.__path__, prefix="app.", onerror=None
    ):
        try:
            importlib.import_module(name)
        except ImportError:
            pass  # optional / platform-specific dependency absent — OK
        except Exception as exc:
            bad.append(f"{name}: {type(exc).__name__}: {exc}")

    assert not bad, "Modules that raised on import:\n" + "\n".join(bad)


async def test_generate_morning_briefing_does_not_crash():
    """BriefingService.generate_morning_briefing() must return a dict, not raise."""
    import app.db as _db

    async with _db.engine.begin() as conn:
        await conn.run_sync(_db.Base.metadata.create_all)

    try:
        from app.services.briefing import get_briefing_service

        briefing = await get_briefing_service().generate_morning_briefing()
        assert isinstance(briefing, dict)
        assert briefing.get("type") == "morning"
    finally:
        async with _db.engine.begin() as conn:
            await conn.run_sync(_db.Base.metadata.drop_all)


async def test_check_due_reminders_does_not_crash():
    """check_due_reminders() must succeed with a live async_session, not short-circuit
    with a None guard and not raise TypeError."""
    import app.db as _db

    async with _db.engine.begin() as conn:
        await conn.run_sync(_db.Base.metadata.create_all)

    try:
        from app.scheduler import check_due_reminders

        await check_due_reminders()
        # No assertion beyond "did not raise"
    finally:
        async with _db.engine.begin() as conn:
            await conn.run_sync(_db.Base.metadata.drop_all)
