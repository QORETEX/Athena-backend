from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    debug: bool = False

    # Database
    database_url: str = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'athena.db'}"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: int = 120

    # TTS
    piper_model_path: str = str(PROJECT_ROOT / "models" / "en_US-lessac-medium.onnx")
    piper_sample_rate: int = 22050

    # STT
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # VAD
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 700

    # Memory
    chroma_persist_dir: str = str(PROJECT_ROOT / "chroma_data")
    embedding_model: str = "all-MiniLM-L6-v2"

    # Smart Home
    hass_url: str = "http://homeassistant.local:8123"
    hass_token: str = ""

    # Web Search
    searxng_url: str = "http://localhost:8080"

    # Weather
    weather_api_url: str = "https://api.open-meteo.com/v1/forecast"
    default_latitude: float | None = None
    default_longitude: float | None = None

    # Image Generation
    image_gen_enabled: bool = False
    stable_diffusion_model: str = "stabilityai/stable-diffusion-2-1"
    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-2.0-flash-exp"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_days: int = 30
    google_client_id: str = ""
    apple_client_id: str = ""

    # Knowledge
    knowledge_collection: str = "athena_knowledge"
    knowledge_chunk_size: int = 500
    knowledge_chunk_overlap: int = 50

    # Claude API (for autonomous agent)
    anthropic_api_key: str = ""
    claude_model: str = "claude-3-5-haiku-20241022"  # Fast & cheap for autonomous loop

    # Groq API (fast and free alternative)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"  # Fast, free, clean responses (Sept 2026)

    # NVIDIA NIM API (free AI models)
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"  # Free, high quality

    # CORS — comma-separated list of allowed frontend origins
    cors_origins: str = "http://localhost:3000,http://localhost:8081,http://localhost:19006"

    # Google OAuth token storage directory
    google_token_dir: str = "./secrets"

    # WebSocket audio buffer size limit (bytes)
    ws_max_audio_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Rate limiting for LLM/external-API routes
    rate_limit_llm: str = "20/minute"
    # Stricter limit for image generation (Gemini/SD are expensive)
    rate_limit_image: str = "5/minute"

    # Proxy trust — set true only when behind Render/trusted reverse proxy.
    # When true, the RIGHTMOST X-Forwarded-For entry is used as the client IP
    # (Render appends the real IP there).  When false, X-Forwarded-For is ignored.
    trust_proxy: bool = False

    # Max concurrent /ws/voice connections per client IP
    ws_max_conn_per_ip: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
