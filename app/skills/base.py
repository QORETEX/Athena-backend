import json
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union


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
    """Return tool descriptors for all currently-available skills (including client_executed)."""
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
        if s.is_available()
    ]


def get_server_tools() -> list[dict]:
    """Return tool descriptors for server-executable skills only.

    Excludes client_executed skills — use this for HTTP endpoints where the
    server handles all tool calls directly.  The WebSocket voice endpoint uses
    get_ollama_tools() instead because it can delegate client_executed tools
    back to the connected device via the TOOL_RESULT_CLIENT protocol message.
    """
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
        if s.is_available() and not s.client_executed
    ]
