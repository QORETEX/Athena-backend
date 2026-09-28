from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Environment ──────────────────────────────────────────────
    # Unset defaults to production so a misconfigured deploy fails loudly.
    environment: Literal["development", "production"] = "production"

    # ── Server ───────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    debug: bool = False
    log_sql: bool = False

    # ── Database ─────────────────────────────────────────────────
    # Empty → SQLite default in development; required (non-SQLite) in production.
    database_url: str = ""

    # ── Ollama (local LLM) ───────────────────────────────────────
    # Empty disables Ollama — no connection attempt, no timeout wait.
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
    # Both empty → smart home disabled; routes return 503.
    hass_url: str = ""
    hass_token: str = ""

    # ── Web Search (SearXNG) ─────────────────────────────────────
    # Empty → web search disabled; skill returns "not configured".
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
    jwt_expiry_days: int = 30
    google_client_id: str = ""
    apple_client_id: str = ""

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

    # ── NVIDIA NIM API ───────────────────────────────────────────
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"

    # ── CORS ─────────────────────────────────────────────────────
    # Empty → no origins allowed (dev: configure in .env; prod: required).
    cors_origins: str = ""

    # ── Google OAuth ─────────────────────────────────────────────
    google_token_dir: str = "./secrets"

    # ── WebSocket limits ─────────────────────────────────────────
    ws_max_audio_bytes: int = 10 * 1024 * 1024  # 10 MB
    ws_max_conn_per_ip: int = 3

    # ── Rate limiting ────────────────────────────────────────────
    rate_limit_llm: str = "20/minute"
    rate_limit_image: str = "5/minute"

    # ── Proxy trust ──────────────────────────────────────────────
    # Set true only when behind a trusted reverse proxy (e.g. Render).
    trust_proxy: bool = False

    # ── IP debug route ───────────────────────────────────────────
    debug_client_ip: bool = False

    # ── Validation ───────────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_and_fill_defaults(self) -> "Settings":
        errors: list[str] = []

        # Development: fill in safe defaults for empty required fields.
        if self.environment == "development":
            if not self.database_url:
                self.database_url = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'athena.db'}"
            if not self.jwt_secret:
                # 32 random bytes → 64-char hex string
                self.jwt_secret = secrets.token_hex(32)

        # Both environments: a Groq key is useless without a model name.
        if self.groq_api_key and not self.groq_model:
            errors.append("GROQ_API_KEY is set but GROQ_MODEL is empty")

        # Production-only strict checks.
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
        """True when OLLAMA_BASE_URL is set; no connection is attempted when False."""
        return bool(self.ollama_base_url)

    @property
    def smart_home_enabled(self) -> bool:
        """True when both HASS_URL and HASS_TOKEN are set."""
        return bool(self.hass_url and self.hass_token)

    @property
    def web_search_enabled(self) -> bool:
        """True when SEARXNG_URL is set."""
        return bool(self.searxng_url)

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed CORS_ORIGINS as a list, stripped of whitespace."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def any_llm_configured(self) -> bool:
        """True when at least one LLM provider is available."""
        return bool(
            self.anthropic_api_key
            or self.groq_api_key
            or self.nvidia_api_key
            or self.ollama_enabled
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
