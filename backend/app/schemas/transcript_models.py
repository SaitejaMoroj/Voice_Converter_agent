from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Language = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
Status = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class TranscriptionCreate(BaseModel):
    title: Title = "Untitled session"
    transcript_text: str = ""
    detected_language: Language | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    status: Status = "completed"
    metadata: dict[str, Any] | None = None


class TranscriptionUpdate(BaseModel):
    title: Title
    transcript_text: str


class TranscriptionPatch(BaseModel):
    title: Title | None = None
    transcript_text: str | None = None
    detected_language: Language | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    status: Status | None = None
    metadata: dict[str, Any] | None = None


class TranscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    title: str
    transcript_text: str
    detected_language: str | None
    duration_seconds: float | None
    status: str
    created_at: datetime
    updated_at: datetime
    audio_available: bool = False
    audio_url: str | None = None
    metadata: dict[str, Any] | None = Field(
        validation_alias="transcription_metadata", serialization_alias="metadata"
    )


class TranscriptionPage(BaseModel):
    records: list[TranscriptionRead]
    total_count: int
    page: int
    page_size: int
    total_pages: int


class TranscriptionStatistics(BaseModel):
    total_sessions: int
    total_duration_seconds: float
    unique_languages: int
    sessions_this_month: int


class TranscriptionBulkDelete(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=100)


class TranscriptionBulkDeleteResult(BaseModel):
    deleted_count: int
