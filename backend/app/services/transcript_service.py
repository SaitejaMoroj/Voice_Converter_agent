from uuid import UUID

from fastapi import HTTPException, status

from app.models.transcript import Transcription
from app.repositories.transcript_store import TranscriptionRepository
from app.schemas.transcript import TranscriptCreate
from app.schemas.transcript_models import TranscriptionCreate


class TranscriptService:
    def __init__(self, repository: TranscriptionRepository) -> None:
        self.repository = repository

    async def list(self, limit: int, offset: int) -> tuple[list[Transcription], int]:
        rows, total = await self.repository.list(
            page=offset // limit + 1, page_size=limit, search=None, sort_by="created_at", sort_order="desc"
        )
        return rows, total

    async def get(self, transcript_id: UUID) -> Transcription:
        transcription = await self.repository.get(transcript_id)
        if transcription is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
        return transcription

    async def create(self, data: TranscriptCreate) -> Transcription:
        return await self.repository.create(TranscriptionCreate(
            title=data.title,
            transcript_text=data.content,
            detected_language=data.language,
            duration_seconds=float(data.duration_seconds),
            status="completed",
        ))

    async def delete(self, transcript_id: UUID) -> None:
        await self.repository.delete(await self.get(transcript_id))
