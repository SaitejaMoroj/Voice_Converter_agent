from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "VoxFlow API"
    database_url: str = "sqlite+aiosqlite:///./var/voxflow.db"
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
