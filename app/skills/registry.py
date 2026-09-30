"""Single entry point for skill module registration."""
import logging

logger = logging.getLogger(__name__)

_registered = False


def register_all_skills() -> None:
    """Import and register every skill module.

    Idempotent: safe to call multiple times — returns immediately after first run.
    The app's lifespan calls this, and so does the test conftest fixture.
    """
    global _registered
    if _registered:
        return
    _registered = True

    from app.skills import (  # noqa: F401
        background_task,
        calendar,
        device_context,
        device_control,
        image_gen,
        knowledge_search,
        notes,
        reminders,
        smart_home,
        vision,
        weather,
        web_search,
    )

    from app.skills.base import get_all_skills

    _skills = get_all_skills()
    _available = [name for name, s in _skills.items() if s.is_available()]
    _unavailable = [
        f"{name} ({s.get_unavailable_reason()})"
        for name, s in _skills.items()
        if not s.is_available()
    ]

    logger.info("Available skills (%d): %s", len(_available), ", ".join(_available))
    logger.info(
        "Unavailable skills: %s",
        ", ".join(_unavailable) if _unavailable else "none",
    )
