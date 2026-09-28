"""Import all skill modules to trigger registration at startup."""
import logging

logger = logging.getLogger(__name__)

from app.skills import (  # noqa: E402, F401
    background_task,
    calendar,
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

from app.skills.base import get_all_skills  # noqa: E402

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
