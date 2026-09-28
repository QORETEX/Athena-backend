import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Skill:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Optional[Callable] = None
    client_executed: bool = False
    timeout: float = 30.0
    # True when the result may contain externally-authored free text that the
    # LLM should not treat as instructions (web snippets, calendar event titles,
    # user-uploaded documents, client-device data, etc.)
    returns_external_content: bool = False


_registry: dict[str, Skill] = {}


def register_skill(skill: Skill):
    _registry[skill.name] = skill


def get_skill(name: str) -> Optional[Skill]:
    return _registry.get(name)


def get_all_skills() -> dict[str, Skill]:
    return _registry.copy()


def serialize_tool_result(skill: Optional[Skill], tool_name: str, result: object) -> str:
    """Serialize a tool result for the message context.
    When the skill's result may contain externally-authored text, wrap it so the
    LLM treats it as data only, never as instructions.
    """
    raw = json.dumps(result)
    if skill is not None and skill.returns_external_content:
        return f'<untrusted_content source="{tool_name}">{raw}</untrusted_content>'
    return raw


def get_ollama_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters,
            },
        }
        for s in _registry.values()
    ]
