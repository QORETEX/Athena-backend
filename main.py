import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db import init_db
from app.logging_config import setup_logging
from app.middleware.access_log import AccessLogMiddleware
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

# Paths that do not require authentication.
PUBLIC_ROUTES: frozenset[str] = frozenset({
    "/health",
    "/api/auth/google",
    "/api/auth/apple",
    "/api/auth/refresh",
    "/api/auth/register",
    "/api/auth/login",
})


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level, settings.debug, settings.log_sql)
    logger.info("Athena backend starting up")

    _db_dialect = settings.database_url.split("+")[0].split(":")[0] if settings.database_url else "none"
    _providers = [n for n, v in [
        ("claude", settings.anthropic_api_key),
        ("groq", settings.groq_api_key),
        ("nvidia", settings.nvidia_api_key),
    ] if v] + (["ollama"] if settings.ollama_enabled else [])
    _integrations = [n for n, ok in [
        ("smart_home", settings.smart_home_enabled),
        ("web_search", settings.web_search_enabled),
        ("image_gen", settings.image_gen_enabled),
    ] if ok]
    logger.info(
        "Config: env=%s db=%s llm=[%s] integrations=[%s]",
        settings.environment,
        _db_dialect,
        ",".join(_providers) or "none",
        ",".join(_integrations) or "none",
    )

    await init_db(settings.database_url)

    from app.scheduler import start_scheduler, shutdown_scheduler

    start_scheduler()

    import app.skills.registry  # noqa: F401

    from app.routines.engine import load_routines

    await load_routines()

    from app.tasks.runner import start_task_worker, stop_task_worker

    await start_task_worker()

    from app.proactive.monitor import start_monitor, stop_monitor

    await start_monitor()

    from app.autonomous.jarvis_brain import start_jarvis_brain, stop_jarvis_brain

    await start_jarvis_brain()

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


_settings = get_settings()
setup_logging(_settings.log_level, _settings.debug, _settings.log_sql)

_is_dev = _settings.environment != "production"

app = FastAPI(
    title="Athena Voice Assistant",
    description="Local-first AI assistant backend — proactive, ambient, context-aware",
    version="2.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
    # Disable interactive docs in production.
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": str(exc)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Must be added AFTER CORSMiddleware so Starlette places it outermost:
# request flow → AccessLog → CORS → ExceptionMiddleware → routes
app.add_middleware(AccessLogMiddleware)

# ── Route imports ────────────────────────────────────────────────

from app.auth.password import router as password_router
from app.routes.auth import protected_router as auth_protected_router
from app.routes.auth import public_router as auth_public_router
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

# ── Public routes (no authentication required) ───────────────────

app.include_router(health_router)
app.include_router(auth_public_router)
app.include_router(password_router)

# ── Protected routes (every route requires get_current_user) ─────

_auth = [Depends(get_current_user)]

app.include_router(auth_protected_router, dependencies=_auth)
app.include_router(skills_router, dependencies=_auth)
app.include_router(chat_router, dependencies=_auth)
app.include_router(context_router, dependencies=_auth)
app.include_router(push_router, dependencies=_auth)
app.include_router(briefing_enhanced_router, dependencies=_auth)
app.include_router(memory_enhanced_router, dependencies=_auth)
app.include_router(patterns_router, dependencies=_auth)
app.include_router(emails_router, dependencies=_auth)
app.include_router(calendar_router, dependencies=_auth)
app.include_router(journal_router, dependencies=_auth)
app.include_router(commute_router, dependencies=_auth)
app.include_router(wellness_router, dependencies=_auth)
app.include_router(automation_router, dependencies=_auth)
app.include_router(relationships_router, dependencies=_auth)
app.include_router(focus_router, dependencies=_auth)
app.include_router(shortcuts_router, dependencies=_auth)
app.include_router(learning_router, dependencies=_auth)
app.include_router(image_router, dependencies=_auth)
app.include_router(reminders_router, dependencies=_auth)
app.include_router(notes_router, dependencies=_auth)
app.include_router(weather_router, dependencies=_auth)
app.include_router(search_router, dependencies=_auth)
app.include_router(knowledge_router, dependencies=_auth)
app.include_router(memory_router, dependencies=_auth)
app.include_router(smart_home_router, dependencies=_auth)
app.include_router(vision_router, dependencies=_auth)
app.include_router(conversations_router, dependencies=_auth)
app.include_router(briefing_router, dependencies=_auth)
app.include_router(routines_router, dependencies=_auth)
app.include_router(tasks_router, dependencies=_auth)
app.include_router(preferences_router, dependencies=_auth)
app.include_router(notifications_router, dependencies=_auth)

# WebSocket routes: auth is enforced inside the handler (first message).
app.include_router(voice_router)
app.include_router(events_router)

if _settings.debug_client_ip:
    from app.routes.debug import router as debug_router
    app.include_router(debug_router, dependencies=_auth)

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
