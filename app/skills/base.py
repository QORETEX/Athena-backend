from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Public view of a skill — returned by skills_for() and GET /api/skills."""
    name: str
    summary: str
    description: str
    parameters: dict[str, Any]
    client_executed: bool
    available: bool
    unavailable_reason: str | None


@dataclass
class Skill:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Optional[Callable] = None
    # One short user-facing phrase; no internal tech names. Required at registration.
    summary: str = ""
    client_executed: bool = False
    timeout: float = 30.0
    # True when the result may contain externally-authored free text that the
    # LLM should not treat as instructions (web snippets, calendar event titles,
    # user-uploaded documents, client-device data, etc.)
    returns_external_content: bool = False
    # Called at tool-list build time; None means always offer.
    enabled_check: Optional[Callable[[], bool]] = None
    # Shown in startup log when is_available() is False. Can be a static string
    # or a callable for reasons that depend on current config (e.g. which key is missing).
    unavailable_reason: Union[str, Callable[[], str]] = ""

    def is_available(self) -> bool:
        """True when this skill should be offered to the LLM."""
        return self.enabled_check is None or self.enabled_check()

    def get_unavailable_reason(self) -> str:
        if callable(self.unavailable_reason):
            return self.unavailable_reason()
        return self.unavailable_reason


_registry: dict[str, Skill] = {}


def register_skill(skill: Skill):
    if not skill.summary:
        raise ValueError(
            f"Skill '{skill.name}' must have a non-empty summary. "
            "Add summary='One short phrase' to the Skill constructor."
        )
    _registry[skill.name] = skill


def get_skill(name: str) -> Optional[Skill]:
    return _registry.get(name)


def get_all_skills() -> dict[str, Skill]:
    return _registry.copy()


def skills_for(client_capabilities: bool = False, user: object = None) -> list[SkillInfo]:
    """Single source of truth for skill availability.

    Returns every registered skill enriched with runtime availability.

    client_capabilities=False → client_executed skills are marked unavailable
        (HTTP text/audio paths cannot relay tool calls to the device).
    client_capabilities=True  → client_executed skills are marked available
        (WS voice path can delegate them to the connected device).
    """
    result: list[SkillInfo] = []
    for s in _registry.values():
        available = s.is_available()
        reason: str | None = None

        if not available:
            reason = s.get_unavailable_reason() or "disabled"
        elif s.client_executed and not client_capabilities:
            available = False
            reason = "requires client connection (use the WebSocket voice channel)"

        result.append(SkillInfo(
            name=s.name,
            summary=s.summary,
            description=s.description,
            parameters=s.parameters,
            client_executed=s.client_executed,
            available=available,
            unavailable_reason=reason,
        ))
    return result


def _skill_info_to_tool_dict(s: SkillInfo) -> dict:
    return {
        "type": "function",
        "function": {
            "name": s.name,
            "description": s.description,
            "parameters": s.parameters,
        },
    }


def serialize_tool_result(skill: Optional[Skill], tool_name: str, result: object) -> str:
    """Serialize a tool result for the message context.
    When the skill's result may contain externally-authored text, wrap it so the
    LLM treats it as data only, never as instructions.
    """
    raw = json.dumps(result)
    if skill is not None and skill.returns_external_content:
        return f'<untrusted_content source="{tool_name}">{raw}</untrusted_content>'
    return raw


def validate_tool_args(skill: Skill, raw_args: dict) -> tuple[dict, str | None]:
    """Validate and clean tool arguments against the skill's parameter schema.

    Drops empty-string keys and keys not declared in the schema (logs at DEBUG).
    Coerces string values to int/float for integer/number typed properties.
    Returns (cleaned_args, error_message) where error_message is None on success
    or a human-readable string describing the first validation failure.
    """
    schema = skill.parameters
    properties: dict[str, Any] = schema.get("properties", {})
    required: list[str] = schema.get("required", [])

    cleaned: dict[str, Any] = {}
    for k, v in raw_args.items():
        if not k:
            logger.debug("Skill %s: dropping empty-key argument", skill.name)
            continue
        if k not in properties:
            logger.debug("Skill %s: dropping unknown argument %r", skill.name, k)
            continue
        prop = properties[k]
        if prop.get("type") == "integer" and isinstance(v, str):
            try:
                v = int(v)
            except (ValueError, TypeError):
                pass
        elif prop.get("type") == "number" and isinstance(v, str):
            try:
                v = float(v)
            except (ValueError, TypeError):
                pass
        cleaned[k] = v

    missing = [r for r in required if r not in cleaned]
    if missing:
        return cleaned, (
            f"missing required parameter(s): {', '.join(repr(m) for m in missing)}"
        )

    return cleaned, None


async def call_skill_handler(skill: Skill, tool_name: str, raw_args: dict) -> dict:
    """Validate arguments and call a skill's server-side handler.

    Returns a structured result dict.  Never raises — exceptions are caught and
    returned as {"error": "..."} so the model can attempt self-correction.
    Does NOT handle client_executed skills; callers must check that flag first.
    """
    validated, err = validate_tool_args(skill, raw_args)
    if err is not None:
        schema = skill.parameters
        props = schema.get("properties", {})
        required: list[str] = schema.get("required", [])
        expected = {k: props[k].get("type", "any") for k in required}
        return {"error": err, "expected": expected}

    if not skill.handler:
        return {"error": f"Skill '{tool_name}' has no handler"}

    try:
        handler_result = skill.handler(**validated)
        if asyncio.iscoroutine(handler_result):
            return await asyncio.wait_for(handler_result, timeout=skill.timeout)
        return handler_result
    except asyncio.TimeoutError:
        return {"error": f"Skill '{tool_name}' timed out"}
    except Exception as e:
        logger.exception("Skill %s failed", tool_name)
        return {"error": str(e)}


def get_ollama_tools() -> list[dict]:
    """Return tool descriptors for all currently-available skills (including client_executed)."""
    return [_skill_info_to_tool_dict(s) for s in skills_for(client_capabilities=True) if s.available]


def get_server_tools() -> list[dict]:
    """Return tool descriptors for server-executable skills only.

    Excludes client_executed skills — use this for HTTP endpoints where the
    server handles all tool calls directly.  The WebSocket voice endpoint uses
    get_ollama_tools() instead because it can delegate client_executed tools
    back to the connected device via the TOOL_RESULT_CLIENT protocol message.
    """
    return [_skill_info_to_tool_dict(s) for s in skills_for(client_capabilities=False) if s.available]
