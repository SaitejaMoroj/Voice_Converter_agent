from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TranscriptCreate(BaseModel):
    title: str = Field(default="Untitled session", min_length=1, max_length=200)
    content: str = Field(min_length=0)
    language: str = Field(default="auto", max_length=16)
    duration_seconds: int = Field(default=0, ge=0)


class TranscriptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    content: str
    language: str
    duration_seconds: int
    created_at: datetime


class TranscriptList(BaseModel):
    items: list[TranscriptRead]
    total: int
