"""Tests for skill availability filtering."""
import pytest
from app.skills.base import Skill, _registry, get_ollama_tools


def test_is_available_no_check():
    """Skill with no enabled_check is always available."""
    skill = Skill(
        name="_test_no_check",
        description="test",
        parameters={"type": "object", "properties": {}},
    )
    assert skill.is_available() is True


def test_is_available_true_check():
    """Skill with enabled_check returning True is available."""
    skill = Skill(
        name="_test_true",
        description="test",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: True,
    )
    assert skill.is_available() is True


def test_is_available_false_check():
    """Skill with enabled_check returning False is unavailable."""
    skill = Skill(
        name="_test_false",
        description="test",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: False,
    )
    assert skill.is_available() is False


def test_unavailable_skill_excluded_from_tool_list():
    """A skill with enabled_check=False must not appear in the LLM tool list."""
    test_skill = Skill(
        name="_test_unavailable",
        description="never offered",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: False,
        unavailable_reason="test only",
    )

    _registry["_test_unavailable"] = test_skill
    try:
        tool_names = {t["function"]["name"] for t in get_ollama_tools()}
        assert "_test_unavailable" not in tool_names
    finally:
        _registry.pop("_test_unavailable", None)


def test_available_skill_included_in_tool_list():
    """A skill with no enabled_check must appear in the LLM tool list."""
    test_skill = Skill(
        name="_test_available",
        description="always offered",
        parameters={"type": "object", "properties": {}},
    )

    _registry["_test_available"] = test_skill
    try:
        tool_names = {t["function"]["name"] for t in get_ollama_tools()}
        assert "_test_available" in tool_names
    finally:
        _registry.pop("_test_available", None)


def test_get_unavailable_reason_static():
    """get_unavailable_reason returns the static string."""
    skill = Skill(
        name="_test",
        description="test",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: False,
        unavailable_reason="SEARXNG_URL not set",
    )
    assert skill.get_unavailable_reason() == "SEARXNG_URL not set"


def test_get_unavailable_reason_callable():
    """get_unavailable_reason calls a callable reason."""
    skill = Skill(
        name="_test",
        description="test",
        parameters={"type": "object", "properties": {}},
        enabled_check=lambda: False,
        unavailable_reason=lambda: "dynamic reason",
    )
    assert skill.get_unavailable_reason() == "dynamic reason"
