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


_registry: dict[str, Skill] = {}


def register_skill(skill: Skill):
    _registry[skill.name] = skill


def get_skill(name: str) -> Optional[Skill]:
    return _registry.get(name)


def get_all_skills() -> dict[str, Skill]:
    return _registry.copy()


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
