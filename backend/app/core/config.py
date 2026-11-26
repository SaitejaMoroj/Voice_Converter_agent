from functools import lru_cache

from pydantic import AliasChoices, Field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(database_url: str) -> str:
    """Return an async SQLAlchemy URL without exposing or rewriting credentials."""
    value = database_url.strip()
    if not value:
        return ""

    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]

    if value.startswith("postgresql+psycopg2://"):
        value = "postgresql+asyncpg://" + value[len("postgresql+psycopg2://"):]
    elif value.startswith("postgresql+psycopg://"):
        value = "postgresql+asyncpg://" + value[len("postgresql+psycopg://"):]
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value[len("postgresql://"):]

    if not value.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
        return value

    if not value.startswith("postgresql+asyncpg://"):
        return value

    parts = urlsplit(value)
    if not parts.query:
        return value

    query = []
    ssl_required = False
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() == "sslmode":
            ssl_required = item.lower() in {"require", "verify-ca", "verify-full"}
        elif key.lower() != "ssl":
            query.append((key, item))
    if ssl_required:
        query.append(("ssl", "true"))

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "VoxFlow API"
    database_url: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL", "database_url"))
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    model_size: str = Field(default="base", validation_alias=AliasChoices("MODEL_SIZE", "WHISPER_MODEL"))
    device: str = Field(default="cpu", validation_alias=AliasChoices("DEVICE", "WHISPER_DEVICE"))
    compute_type: str = Field(default="int8", validation_alias=AliasChoices("COMPUTE_TYPE", "WHISPER_COMPUTE_TYPE"))
    default_language: str = "en"
    enable_language_detection: bool = True
    audio_sample_rate: int = Field(default=16_000, ge=8_000, le=48_000)
    audio_window_seconds: int = Field(default=3, ge=1, le=30)
    audio_overlap_seconds: float = Field(default=0.75, ge=0)
    websocket_max_chunk_bytes: int = Field(default=262_144, ge=2, le=4_194_304)
    websocket_max_session_seconds: int = Field(default=3_600, ge=1, le=86_400)
    websocket_idle_timeout_seconds: int = Field(default=60, ge=1, le=3_600)
    websocket_start_timeout_seconds: int = Field(default=15, ge=1, le=300)
    websocket_autosave_windows: int = Field(default=2, ge=1, le=20)
    audio_storage_dir: str = "var/audio"
    audio_max_upload_bytes: int = Field(default=250_000_000, ge=1_024, le=1_000_000_000)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
