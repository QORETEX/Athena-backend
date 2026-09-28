"""Tests for Settings validation logic."""
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings

# All field names that pydantic-settings reads from the environment.
# Cleared in clean_env so shell variables don't bleed into tests.
_ALL_SETTINGS_KEYS = [
    "ENVIRONMENT", "HOST", "PORT", "LOG_LEVEL", "DEBUG", "LOG_SQL",
    "DATABASE_URL",
    "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_TIMEOUT",
    "PIPER_MODEL_PATH", "PIPER_SAMPLE_RATE",
    "WHISPER_MODEL_SIZE", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE",
    "VAD_THRESHOLD", "VAD_MIN_SILENCE_MS",
    "CHROMA_PERSIST_DIR", "EMBEDDING_MODEL",
    "HASS_URL", "HASS_TOKEN",
    "SEARXNG_URL",
    "WEATHER_API_URL", "DEFAULT_LATITUDE", "DEFAULT_LONGITUDE",
    "IMAGE_GEN_ENABLED", "STABLE_DIFFUSION_MODEL",
    "GEMINI_API_KEY", "GEMINI_IMAGE_MODEL",
    "JWT_SECRET",
    "ACCESS_TOKEN_TTL_MINUTES", "REFRESH_TOKEN_TTL_DAYS",
    "GOOGLE_CLIENT_ID", "APPLE_CLIENT_ID",
    "PASSWORD_AUTH_ENABLED", "RATE_LIMIT_AUTH",
    "KNOWLEDGE_COLLECTION", "KNOWLEDGE_CHUNK_SIZE", "KNOWLEDGE_CHUNK_OVERLAP",
    "ANTHROPIC_API_KEY", "CLAUDE_MODEL",
    "GROQ_API_KEY", "GROQ_MODEL",
    "NVIDIA_API_KEY", "NVIDIA_MODEL",
    "CORS_ORIGINS",
    "GOOGLE_TOKEN_DIR",
    "WS_MAX_AUDIO_BYTES", "WS_MAX_CONN_PER_IP",
    "RATE_LIMIT_LLM", "RATE_LIMIT_IMAGE",
    "TRUST_PROXY", "DEBUG_CLIENT_IP",
]

# Minimum set of fields needed for a valid production config.
_VALID_PROD = dict(
    environment="production",
    database_url="postgresql+asyncpg://user:pass@host/db",
    jwt_secret="a" * 64,
    cors_origins="https://app.example.com",
    groq_api_key="gsk_test_key_valid",
    groq_model="openai/gpt-oss-20b",
    google_client_id="test.apps.googleusercontent.com",
    debug=False,
)


@pytest.fixture
def clean_env(monkeypatch):
    """Clear every Settings-related env var so only constructor kwargs matter."""
    for key in _ALL_SETTINGS_KEYS:
        monkeypatch.delenv(key, raising=False)


# ── Production validation ─────────────────────────────────────────────────────


def test_production_empty_jwt(clean_env):
    with pytest.raises(Exception, match="JWT_SECRET"):
        Settings(_env_file=None, **{**_VALID_PROD, "jwt_secret": ""})


def test_production_sqlite(clean_env):
    with pytest.raises(Exception, match="SQLite"):
        Settings(_env_file=None, **{**_VALID_PROD, "database_url": "sqlite+aiosqlite:///./athena.db"})


def test_production_no_database_url(clean_env):
    with pytest.raises(Exception, match="DATABASE_URL"):
        Settings(_env_file=None, **{**_VALID_PROD, "database_url": ""})


def test_production_cors_wildcard(clean_env):
    with pytest.raises(Exception, match="CORS_ORIGINS"):
        Settings(_env_file=None, **{**_VALID_PROD, "cors_origins": "*"})


def test_production_cors_localhost(clean_env):
    with pytest.raises(Exception, match="localhost"):
        Settings(_env_file=None, **{**_VALID_PROD, "cors_origins": "http://localhost:3000"})


def test_production_no_llm(clean_env):
    with pytest.raises(Exception, match="LLM provider"):
        Settings(_env_file=None, **{
            **_VALID_PROD,
            "groq_api_key": "",
            "anthropic_api_key": "",
            "nvidia_api_key": "",
            "ollama_base_url": "",
        })


def test_production_ollama_localhost(clean_env):
    with pytest.raises(Exception, match="OLLAMA_BASE_URL"):
        Settings(_env_file=None, **{**_VALID_PROD, "ollama_base_url": "http://localhost:11434"})


def test_production_hass_dotlocal(clean_env):
    with pytest.raises(Exception, match="HASS_URL"):
        Settings(_env_file=None, **{**_VALID_PROD, "hass_url": "http://homeassistant.local:8123"})


def test_production_debug_true(clean_env):
    with pytest.raises(Exception, match="DEBUG"):
        Settings(_env_file=None, **{**_VALID_PROD, "debug": True})


# ── Groq model check (both environments) ─────────────────────────────────────


def test_groq_key_without_model_development(clean_env):
    with pytest.raises(Exception, match="GROQ_MODEL"):
        Settings(_env_file=None, environment="development", groq_api_key="gsk_test", groq_model="")


def test_groq_key_without_model_production(clean_env):
    with pytest.raises(Exception, match="GROQ_MODEL"):
        Settings(_env_file=None, **{**_VALID_PROD, "groq_model": ""})


# ── Happy paths ───────────────────────────────────────────────────────────────


def test_valid_production_config(clean_env):
    s = Settings(_env_file=None, **_VALID_PROD)
    assert s.environment == "production"
    assert s.any_llm_configured


def test_empty_development_config(clean_env):
    s = Settings(_env_file=None, environment="development")
    assert "sqlite" in s.database_url
    assert len(s.jwt_secret) == 64


def test_environment_unset_defaults_to_production(clean_env):
    """ENVIRONMENT unset → production validation fires and rejects missing required fields."""
    with pytest.raises(Exception):
        # No ENVIRONMENT kwarg → defaults to "production" → validator requires DATABASE_URL etc.
        Settings(_env_file=None)


# ── Derived properties ────────────────────────────────────────────────────────


def test_ollama_enabled_when_url_set(clean_env):
    s = Settings(_env_file=None, environment="development", ollama_base_url="http://gpu-server:11434")
    assert s.ollama_enabled is True


def test_ollama_disabled_when_url_empty(clean_env):
    s = Settings(_env_file=None, environment="development", ollama_base_url="")
    assert s.ollama_enabled is False


def test_smart_home_enabled_requires_both(clean_env):
    s_both = Settings(_env_file=None, environment="development", hass_url="http://ha:8123", hass_token="tok")
    assert s_both.smart_home_enabled is True

    s_url_only = Settings(_env_file=None, environment="development", hass_url="http://ha:8123", hass_token="")
    assert s_url_only.smart_home_enabled is False

    s_neither = Settings(_env_file=None, environment="development")
    assert s_neither.smart_home_enabled is False


def test_web_search_enabled(clean_env):
    s_on = Settings(_env_file=None, environment="development", searxng_url="http://search:8080")
    assert s_on.web_search_enabled is True

    s_off = Settings(_env_file=None, environment="development", searxng_url="")
    assert s_off.web_search_enabled is False


def test_cors_origin_list_parsed(clean_env):
    s = Settings(
        _env_file=None,
        environment="development",
        cors_origins="https://a.example.com, https://b.example.com , ",
    )
    assert s.cors_origin_list == ["https://a.example.com", "https://b.example.com"]


def test_cors_origin_list_empty(clean_env):
    s = Settings(_env_file=None, environment="development", cors_origins="")
    assert s.cors_origin_list == []
