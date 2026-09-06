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

logger.info("Registered %d skills: %s", len(get_all_skills()), list(get_all_skills().keys()))
