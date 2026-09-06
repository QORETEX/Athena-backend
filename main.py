import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level, settings.debug)
    logger.info("Athena backend starting up")

    await init_db(settings.database_url)

    from app.scheduler import start_scheduler, shutdown_scheduler

    start_scheduler()

    # Trigger skill registration
    import app.skills.registry  # noqa: F401

    # Load saved routines into scheduler
    from app.routines.engine import load_routines

    await load_routines()

    # Start background task worker
    from app.tasks.runner import start_task_worker, stop_task_worker

    await start_task_worker()

    # Start proactive monitoring loop
    from app.proactive.monitor import start_monitor, stop_monitor

    await start_monitor()

    # Start JARVIS autonomous brain (Claude-powered)
    from app.autonomous.jarvis_brain import start_jarvis_brain, stop_jarvis_brain

    await start_jarvis_brain()

    # Initialize preset quick actions
    try:
        from app.db import async_session
        from app.services.quick_actions_service import QuickActionsService

        async with async_session() as session:
            quick_actions = QuickActionsService(session)
            await quick_actions.initialize_preset_actions()
        logger.info("Preset quick actions initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize preset actions: {e}")

    logger.info("Athena backend ready")
    yield

    await stop_jarvis_brain()
    await stop_monitor()
    await stop_task_worker()
    shutdown_scheduler()
    logger.info("Athena backend shut down")


app = FastAPI(
    title="Athena Voice Assistant",
    description="Local-first AI assistant backend — proactive, ambient, context-aware",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────

from app.routes.auth import router as auth_router
from app.routes.automation import router as automation_router
from app.routes.briefing import router as briefing_router
from app.routes.briefing_enhanced import router as briefing_enhanced_router
from app.routes.calendar import router as calendar_router
from app.routes.chat import router as chat_router
from app.routes.commute import router as commute_router
from app.routes.context import router as context_router
from app.routes.conversations import router as conversations_router
from app.routes.emails import router as emails_router
from app.routes.focus import router as focus_router
from app.routes.health import router as health_router
from app.routes.image import router as image_router
from app.routes.journal import router as journal_router
from app.routes.knowledge import router as knowledge_router
from app.routes.learning import router as learning_router
from app.routes.memory import router as memory_router
from app.routes.memory_enhanced import router as memory_enhanced_router
from app.routes.notes import router as notes_router
from app.routes.notifications import router as notifications_router
from app.routes.patterns import router as patterns_router
from app.routes.preferences import router as preferences_router
from app.routes.push import router as push_router
from app.routes.relationships import router as relationships_router
from app.routes.reminders import router as reminders_router
from app.routes.routines import router as routines_router
from app.routes.search import router as search_router
from app.routes.shortcuts import router as shortcuts_router
from app.routes.skills import router as skills_router
from app.routes.smart_home import router as smart_home_router
from app.routes.tasks import router as tasks_router
from app.routes.vision import router as vision_router
from app.routes.weather import router as weather_router
from app.routes.wellness import router as wellness_router
from app.websocket.events import router as events_router
from app.websocket.voice import router as voice_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(skills_router)
app.include_router(chat_router)
app.include_router(context_router)
app.include_router(push_router)
app.include_router(briefing_enhanced_router)
app.include_router(memory_enhanced_router)
app.include_router(patterns_router)
app.include_router(emails_router)
app.include_router(calendar_router)
app.include_router(journal_router)
app.include_router(commute_router)
app.include_router(wellness_router)
app.include_router(automation_router)
app.include_router(relationships_router)
app.include_router(focus_router)
app.include_router(shortcuts_router)
app.include_router(learning_router)
app.include_router(image_router)
app.include_router(reminders_router)
app.include_router(notes_router)
app.include_router(weather_router)
app.include_router(search_router)
app.include_router(knowledge_router)
app.include_router(memory_router)
app.include_router(smart_home_router)
app.include_router(vision_router)
app.include_router(conversations_router)
app.include_router(briefing_router)
app.include_router(routines_router)
app.include_router(tasks_router)
app.include_router(preferences_router)
app.include_router(notifications_router)
app.include_router(voice_router)
app.include_router(events_router)

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
