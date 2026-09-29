from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Environment ──────────────────────────────────────────────
    environment: Literal["development", "production"] = "production"

    # ── Server ───────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    debug: bool = False
    log_sql: bool = False

    # ── Database ─────────────────────────────────────────────────
    database_url: str = ""

    # ── Ollama (local LLM) ───────────────────────────────────────
    ollama_base_url: str = ""
    ollama_model: str = "llama3.2"
    ollama_timeout: int = 120

    # ── TTS ──────────────────────────────────────────────────────
    piper_model_path: str = str(PROJECT_ROOT / "models" / "en_US-lessac-medium.onnx")
    piper_sample_rate: int = 22050

    # ── STT ──────────────────────────────────────────────────────
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # ── VAD ──────────────────────────────────────────────────────
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 700

    # ── Memory ───────────────────────────────────────────────────
    chroma_persist_dir: str = str(PROJECT_ROOT / "chroma_data")
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── Smart Home (Home Assistant) ──────────────────────────────
    hass_url: str = ""
    hass_token: str = ""

    # ── Web Search (SearXNG) ─────────────────────────────────────
    searxng_url: str = ""

    # ── Weather ──────────────────────────────────────────────────
    weather_api_url: str = "https://api.open-meteo.com/v1/forecast"
    default_latitude: float | None = None
    default_longitude: float | None = None

    # ── Image Generation ─────────────────────────────────────────
    image_gen_enabled: bool = False
    stable_diffusion_model: str = "stabilityai/stable-diffusion-2-1"
    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-2.0-flash-exp"

    # ── Auth ─────────────────────────────────────────────────────
    # Empty → auto-generated 64-char hex in development; required in production.
    jwt_secret: str = ""
    # Access token TTL in minutes (short-lived).
    access_token_ttl_minutes: int = 15
    # Refresh token TTL in days (long-lived, stored as hash in DB).
    refresh_token_ttl_days: int = 30
    # Comma-separated OAuth client IDs (web / iOS / Android may differ).
    google_client_id: str = ""
    apple_client_id: str = ""
    # Enable email/password login — test-only; production warning if true.
    password_auth_enabled: bool = False
    # Rate limit applied to all auth endpoints, keyed by IP.
    rate_limit_auth: str = "5/minute"

    # ── Knowledge ────────────────────────────────────────────────
    knowledge_collection: str = "athena_knowledge"
    knowledge_chunk_size: int = 500
    knowledge_chunk_overlap: int = 50

    # ── Claude API ───────────────────────────────────────────────
    anthropic_api_key: str = ""
    claude_model: str = "claude-3-5-haiku-20241022"

    # ── Groq API ─────────────────────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_max_tokens: int = 1024

    # ── NVIDIA NIM API ───────────────────────────────────────────
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nvidia_max_tokens: int = 1024
    # Nemotron reasoning models think before answering; disabling saves 5–30 s per call.
    # Switch: chat_template_kwargs: {"thinking": False}  (verified against live API)
    nvidia_reasoning: bool = False

    # ── LLM timeouts & chain deadline ────────────────────────────
    # Connect timeout: fail fast if the server is unreachable.
    llm_connect_timeout: int = 5
    # Read timeout: max wait for the first response byte after the request is sent.
    llm_read_timeout: int = 25
    # Chain deadline: total budget for the entire Groq→NVIDIA→Ollama fallback sequence.
    # Each provider gets min(llm_read_timeout, remaining_budget) for its read phase.
    # Providers are skipped once the budget is spent.
    llm_chain_deadline: int = 40

    # ── CORS ─────────────────────────────────────────────────────
    cors_origins: str = ""

    # ── Google OAuth ─────────────────────────────────────────────
    google_token_dir: str = "./secrets"

    # ── WebSocket limits ─────────────────────────────────────────
    ws_max_audio_bytes: int = 10 * 1024 * 1024
    ws_max_conn_per_ip: int = 3

    # ── Rate limiting ────────────────────────────────────────────
    rate_limit_llm: str = "20/minute"
    rate_limit_image: str = "5/minute"

    # ── Proxy trust ──────────────────────────────────────────────
    trust_proxy: bool = False

    # ── IP debug route ───────────────────────────────────────────
    debug_client_ip: bool = False

    # ── Access logging ────────────────────────────────────────────
    access_log: bool = True
    # Comma-separated path prefixes excluded from access logging.
    access_log_exclude: str = "/health"

    # ── Validation ───────────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_and_fill_defaults(self) -> "Settings":
        errors: list[str] = []

        if self.environment == "development":
            if not self.database_url:
                self.database_url = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'athena.db'}"
            if not self.jwt_secret:
                self.jwt_secret = secrets.token_hex(32)

        if self.groq_api_key and not self.groq_model:
            errors.append("GROQ_API_KEY is set but GROQ_MODEL is empty")

        if self.environment == "production":
            if not self.jwt_secret:
                errors.append(
                    "JWT_SECRET must be set in production "
                    "(generate with: python -c \"import secrets; print(secrets.token_hex(32))\")"
                )

            if not self.database_url:
                errors.append("DATABASE_URL must be set in production")
            elif "sqlite" in self.database_url.lower():
                errors.append(
                    "DATABASE_URL must not be SQLite in production; use PostgreSQL "
                    "(e.g. postgresql+asyncpg://user:pass@host/db)"
                )

            cors_list = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
            if not cors_list:
                errors.append(
                    "CORS_ORIGINS must be set in production "
                    "(comma-separated list of allowed frontend origins)"
                )
            elif "*" in cors_list:
                errors.append("CORS_ORIGINS must not be '*' in production")
            elif any("localhost" in o or "127.0.0.1" in o for o in cors_list):
                errors.append(
                    "CORS_ORIGINS must not contain localhost or 127.0.0.1 in production"
                )

            if not any([
                self.anthropic_api_key,
                self.groq_api_key,
                self.nvidia_api_key,
                self.ollama_base_url,
            ]):
                errors.append(
                    "At least one LLM provider must be configured in production "
                    "(ANTHROPIC_API_KEY, GROQ_API_KEY, NVIDIA_API_KEY, or OLLAMA_BASE_URL)"
                )

            if not any([
                self.google_client_id,
                self.apple_client_id,
                self.password_auth_enabled,
            ]):
                errors.append(
                    "At least one login method must be configured in production "
                    "(GOOGLE_CLIENT_ID, APPLE_CLIENT_ID, or PASSWORD_AUTH_ENABLED)"
                )

            if self.password_auth_enabled:
                # Warn but allow — test-only feature intentionally enabled.
                logger.warning(
                    "PASSWORD_AUTH_ENABLED is true in production. "
                    "Password login is a test-only feature."
                )

            if self.ollama_base_url and (
                "localhost" in self.ollama_base_url
                or "127.0.0.1" in self.ollama_base_url
            ):
                errors.append(
                    "OLLAMA_BASE_URL must not point to localhost in production"
                )

            if self.hass_url and ".local" in self.hass_url:
                errors.append(
                    "HASS_URL must not use .local hostnames in production; "
                    "use a routable hostname or IP address"
                )

            if self.debug:
                errors.append("DEBUG must be false in production")

        if errors:
            msg = "Invalid configuration:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(msg)

        return self

    # ── Derived properties ────────────────────────────────────────

    @property
    def ollama_enabled(self) -> bool:
        return bool(self.ollama_base_url)

    @property
    def smart_home_enabled(self) -> bool:
        return bool(self.hass_url and self.hass_token)

    @property
    def web_search_enabled(self) -> bool:
        return bool(self.searxng_url)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def any_llm_configured(self) -> bool:
        return bool(
            self.anthropic_api_key
            or self.groq_api_key
            or self.nvidia_api_key
            or self.ollama_enabled
        )

    @property
    def google_client_id_list(self) -> list[str]:
        """Parsed GOOGLE_CLIENT_ID as a list (comma-separated)."""
        return [s.strip() for s in self.google_client_id.split(",") if s.strip()]

    @property
    def apple_client_id_list(self) -> list[str]:
        """Parsed APPLE_CLIENT_ID as a list (comma-separated)."""
        return [s.strip() for s in self.apple_client_id.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
