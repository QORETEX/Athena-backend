"""Tests for tool argument validation and the shared call_skill_handler helper."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.skills.base import Skill, call_skill_handler, validate_tool_args


# ── helpers ────────────────────────────────────────────────────────────────────


def _skill(name="test_tool", properties=None, required=None, handler=None, timeout=5.0):
    params: dict = {"type": "object", "properties": properties or {}}
    if required:
        params["required"] = required
    return Skill(name=name, description="test", parameters=params, handler=handler, timeout=timeout)


# ── validate_tool_args ─────────────────────────────────────────────────────────


def test_empty_key_dropped():
    skill = _skill()  # no declared parameters
    cleaned, err = validate_tool_args(skill, {"": "some_value"})
    assert "" not in cleaned
    assert err is None


def test_unknown_key_dropped():
    skill = _skill(properties={"text": {"type": "string"}}, required=["text"])
    cleaned, err = validate_tool_args(skill, {"text": "hello", "bogus": "x"})
    assert "bogus" not in cleaned
    assert cleaned["text"] == "hello"
    assert err is None


def test_missing_required_returns_error():
    skill = _skill(properties={"time": {"type": "string"}}, required=["time"])
    cleaned, err = validate_tool_args(skill, {})
    assert err is not None
    assert "time" in err


def test_missing_required_error_includes_param_name():
    skill = _skill(
        properties={"text": {"type": "string"}, "time": {"type": "string"}},
        required=["text", "time"],
    )
    _, err = validate_tool_args(skill, {"text": "hi"})
    assert err is not None
    assert "time" in err


def test_integer_coercion():
    skill = _skill(properties={"count": {"type": "integer"}}, required=["count"])
    cleaned, err = validate_tool_args(skill, {"count": "5"})
    assert err is None
    assert cleaned["count"] == 5
    assert isinstance(cleaned["count"], int)


def test_number_coercion():
    skill = _skill(properties={"value": {"type": "number"}}, required=["value"])
    cleaned, err = validate_tool_args(skill, {"value": "3.14"})
    assert err is None
    assert abs(cleaned["value"] - 3.14) < 1e-9


def test_non_coercible_string_kept_as_string():
    """If a string can't be coerced to int, leave it as-is (handler will catch type errors)."""
    skill = _skill(properties={"count": {"type": "integer"}}, required=["count"])
    cleaned, err = validate_tool_args(skill, {"count": "not_a_number"})
    assert err is None
    assert cleaned["count"] == "not_a_number"


def test_valid_args_no_error():
    skill = _skill(
        properties={"text": {"type": "string"}, "time": {"type": "string"}},
        required=["text", "time"],
    )
    cleaned, err = validate_tool_args(skill, {"text": "hi", "time": "2026-10-01T08:00:00+00:00"})
    assert err is None
    assert cleaned == {"text": "hi", "time": "2026-10-01T08:00:00+00:00"}


# ── call_skill_handler ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_key_on_no_parameter_tool():
    """Empty-key argument on a no-parameter tool: key dropped, handler called with no args."""
    handler = AsyncMock(return_value={"reminders": []})
    skill = _skill(handler=handler)
    result = await call_skill_handler(skill, "test_tool", {"": "leftover"})
    assert "error" not in result
    handler.assert_called_once_with()


@pytest.mark.asyncio
async def test_unknown_key_stripped_before_handler_call():
    """Unknown key stripped; handler receives only declared params."""
    handler = AsyncMock(return_value={"ok": True})
    skill = _skill(
        properties={"text": {"type": "string"}},
        required=["text"],
        handler=handler,
    )
    result = await call_skill_handler(skill, "test_tool", {"text": "hi", "extra": "x"})
    assert "error" not in result
    handler.assert_called_once_with(text="hi")


@pytest.mark.asyncio
async def test_missing_required_parameter_returns_error_dict():
    """Missing required param: structured error returned, handler never called."""
    handler = AsyncMock()
    skill = _skill(
        properties={"time": {"type": "string"}},
        required=["time"],
        handler=handler,
    )
    result = await call_skill_handler(skill, "test_tool", {})
    assert "error" in result
    assert "time" in result["error"]
    assert "expected" in result
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_missing_required_error_includes_expected_schema():
    """Error result must include 'expected' field describing required parameters."""
    handler = AsyncMock()
    skill = _skill(
        properties={"time": {"type": "string"}},
        required=["time"],
        handler=handler,
    )
    result = await call_skill_handler(skill, "test_tool", {})
    assert isinstance(result.get("expected"), dict)
    assert "time" in result["expected"]


@pytest.mark.asyncio
async def test_handler_exception_returns_error_dict():
    """Handler raising must return structured error dict, not propagate the exception."""
    async def boom(**kwargs):
        raise ValueError("database error")

    skill = _skill(handler=boom)
    result = await call_skill_handler(skill, "test_tool", {})
    assert "error" in result
    assert "database error" in result["error"]


@pytest.mark.asyncio
async def test_handler_sync_callable():
    """Synchronous (non-async) handlers must also work correctly."""
    def sync_handler(**kwargs):
        return {"result": "sync"}

    skill = _skill(handler=sync_handler)
    result = await call_skill_handler(skill, "test_tool", {})
    assert result == {"result": "sync"}


@pytest.mark.asyncio
async def test_no_handler_returns_error():
    """Skill with no handler returns a structured error, not an AttributeError."""
    skill = _skill(handler=None)
    result = await call_skill_handler(skill, "test_tool", {})
    assert "error" in result
    assert "no handler" in result["error"].lower()
