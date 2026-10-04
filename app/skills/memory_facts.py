"""Per-user persistent memory skills: remember, forget, and list facts."""
from __future__ import annotations

import re
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select

import app.db as _appdb
from app.skills.base import Skill, register_skill

logger = logging.getLogger(__name__)

# Keys that look like sensitive credentials — reject silently with a clear message.
_SENSITIVE_KEY_FRAGMENTS = frozenset({
    "password", "passwd", "passphrase", "pin", "ssn", "social_security",
    "card_number", "credit_card", "debit_card", "cvv", "cvc", "cvv2",
    "bank_account", "routing_number", "passport", "drivers_license",
    "secret", "private_key", "api_key", "token",
})

# Matches 13-19 digit card-number patterns (with optional spaces/dashes).
_CARD_RE = re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b')


def _sensitive_error(key: str, value: str) -> str | None:
    """Return an error string if key or value looks like a sensitive credential."""
    key_norm = key.lower().replace("-", "_").replace(" ", "_")
    for fragment in _SENSITIVE_KEY_FRAGMENTS:
        if fragment in key_norm:
            return (
                f"I can't store values for '{key}' — that looks like a sensitive credential. "
                "I won't store passwords, PINs, card numbers, or similar secrets."
            )
    if _CARD_RE.search(value):
        return "I won't store that — it looks like a payment card number."
    return None


def _get_user_id() -> int | None:
    # Deferred import: pipeline.py imports base.py; this import must not be top-level.
    from app.chat.pipeline import _current_user_id
    return _current_user_id.get()


async def handle_remember_fact(key: str, value: str, category: str = "fact") -> dict:
    user_id = _get_user_id()
    if not user_id:
        return {"success": False, "error": "Not authenticated"}

    err = _sensitive_error(key, value)
    if err:
        return {"success": False, "error": err}

    now = datetime.now(timezone.utc)
    async with _appdb.async_session() as session:
        result = await session.execute(
            select(_appdb.UserKnowledge).where(
                _appdb.UserKnowledge.user_id == user_id,
                _appdb.UserKnowledge.key == key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
            existing.category = category
            existing.updated_at = now
        else:
            session.add(_appdb.UserKnowledge(
                user_id=user_id,
                category=category,
                key=key,
                value=value,
                source="user",
                confidence=1.0,
                verified=True,
                related_knowledge="[]",
                created_at=now,
                updated_at=now,
            ))
        await session.commit()

    return {"success": True, "key": key, "value": value, "category": category}


async def handle_forget_fact(key: str) -> dict:
    user_id = _get_user_id()
    if not user_id:
        return {"success": False, "error": "Not authenticated"}

    async with _appdb.async_session() as session:
        result = await session.execute(
            select(_appdb.UserKnowledge).where(
                _appdb.UserKnowledge.user_id == user_id,
                _appdb.UserKnowledge.key == key,
            )
        )
        fact = result.scalar_one_or_none()
        if not fact:
            return {"success": False, "error": f"No fact found with key '{key}'"}
        await session.delete(fact)
        await session.commit()

    return {"success": True, "key": key}


async def handle_forget_all_facts() -> dict:
    user_id = _get_user_id()
    if not user_id:
        return {"success": False, "error": "Not authenticated"}

    async with _appdb.async_session() as session:
        await session.execute(
            delete(_appdb.UserKnowledge).where(_appdb.UserKnowledge.user_id == user_id)
        )
        await session.commit()

    return {"success": True, "message": "All facts have been forgotten"}


async def handle_list_facts() -> dict:
    user_id = _get_user_id()
    if not user_id:
        return {"success": False, "error": "Not authenticated"}

    async with _appdb.async_session() as session:
        result = await session.execute(
            select(_appdb.UserKnowledge)
            .where(_appdb.UserKnowledge.user_id == user_id)
            .order_by(_appdb.UserKnowledge.updated_at.desc())
            .limit(40)
        )
        facts = result.scalars().all()

    return {
        "facts": [
            {"key": f.key, "value": f.value, "category": f.category}
            for f in facts
        ]
    }


register_skill(Skill(
    name="remember_fact",
    summary="Remember a personal fact about the user",
    description=(
        "Store or update one lasting fact about the user. "
        "Use this when the user shares a personal fact or preference, or explicitly asks you "
        "to remember something. "
        "Example keys: 'name', 'study_program', 'city', 'preferred_language'. "
        "NEVER store passwords, PINs, card or ID numbers, or health details unless the user "
        "explicitly and directly asks you to save that specific sensitive item."
    ),
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Short snake_case identifier for the fact (e.g. 'study_program')",
            },
            "value": {
                "type": "string",
                "description": "The fact value (e.g. 'IT at KNUST')",
            },
            "category": {
                "type": "string",
                "enum": ["fact", "preference", "skill", "relationship"],
                "description": "Fact category (default: fact)",
            },
        },
        "required": ["key", "value"],
    },
    handler=handle_remember_fact,
))

register_skill(Skill(
    name="forget_fact",
    summary="Forget one stored fact",
    description=(
        "Delete one remembered fact by its key. "
        "Call this when the user asks you to forget or stop remembering a specific piece of information."
    ),
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The key of the fact to delete (e.g. 'study_program')",
            },
        },
        "required": ["key"],
    },
    handler=handle_forget_fact,
))

register_skill(Skill(
    name="forget_all_facts",
    summary="Forget all stored facts",
    description=(
        "Delete ALL facts remembered about the user. "
        "Only call this after the user has explicitly confirmed in the current conversation "
        "that they want every remembered fact erased. Do not call this speculatively."
    ),
    parameters={"type": "object", "properties": {}},
    handler=handle_forget_all_facts,
))

register_skill(Skill(
    name="list_facts",
    summary="List what I remember about the user",
    description=(
        "Return the list of facts currently remembered about this user. "
        "Call this when the user asks what you know or remember about them."
    ),
    parameters={"type": "object", "properties": {}},
    handler=handle_list_facts,
))
