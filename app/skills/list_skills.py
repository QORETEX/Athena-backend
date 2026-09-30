from __future__ import annotations

from app.skills.base import Skill, register_skill


async def handle_list_skills() -> dict:
    # Deferred import: pipeline.py imports base.py, so this must not be top-level.
    from app.chat.pipeline import _client_capabilities
    from app.skills.base import skills_for

    client_caps = _client_capabilities.get(False)
    infos = skills_for(client_capabilities=client_caps)
    return {
        "skills": [
            {"name": s.name, "summary": s.summary}
            for s in infos
            if s.available and s.name != "list_skills"
        ]
    }


register_skill(
    Skill(
        name="list_skills",
        summary="List what I can do",
        description=(
            "Return the capabilities available in this session. "
            "Call this whenever the user asks what you can do, what skills or features you have, "
            "whether you can do something specific, or any variation of 'what are your capabilities'. "
            "Answer ONLY from the returned list — do not describe or promise capabilities not in it."
        ),
        parameters={"type": "object", "properties": {}},
        handler=handle_list_skills,
        timeout=5,
    )
)
