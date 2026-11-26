from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Transcription(Base):
    __tablename__ = "transcriptions"
    __table_args__ = (Index("ix_transcriptions_created_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="Untitled session")
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detected_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    transcription_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    audio_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    @property
    def audio_available(self) -> bool:
        return self.audio_storage_key is not None

    @property
    def audio_url(self) -> str | None:
        return f"/api/transcriptions/{self.id}/audio" if self.audio_available else None