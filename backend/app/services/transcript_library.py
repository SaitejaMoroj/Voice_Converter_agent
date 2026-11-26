from __future__ import annotations

import asyncio
import logging
from math import ceil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status

from app.models.transcript import Transcription
from app.repositories.transcript_store import TranscriptionRepository
from app.schemas.transcript_models import TranscriptionCreate, TranscriptionPage, TranscriptionPatch, TranscriptionUpdate
from app.services.audio_storage_service import AudioStorageError, AudioStorageService

logger = logging.getLogger(__name__)


class TranscriptionCrudService:
    def __init__(self, repository: TranscriptionRepository, audio_storage: AudioStorageService | None = None) -> None:
        self.repository = repository
        self.audio_storage = audio_storage or AudioStorageService()

    async def list(
        self, *, page: int, page_size: int, search: str | None, sort_by: str, sort_order: str,
        language: str | None = None, created_after: datetime | None = None, created_before: datetime | None = None,
    ) -> TranscriptionPage:
        records, total_count = await self.repository.list(
            page=page, page_size=page_size, search=search, sort_by=sort_by, sort_order=sort_order,
            language=language, created_after=created_after, created_before=created_before,
        )
        return TranscriptionPage(
            records=records,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=ceil(total_count / page_size) if total_count else 0,
        )

    async def languages(self) -> list[str]:
        return await self.repository.languages()

    async def statistics(self) -> dict[str, int | float]:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return await self.repository.statistics(month_start)

    async def get(self, transcription_id: UUID) -> Transcription:
        transcription = await self.repository.get(transcription_id)
        if transcription is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcription not found")
        return transcription

    async def create(self, data: TranscriptionCreate) -> Transcription:
        return await self.repository.create(data)

    async def replace(self, transcription_id: UUID, data: TranscriptionUpdate) -> Transcription:
        transcription = await self.get(transcription_id)
        return await self.repository.update(transcription, data.model_dump())

    async def patch(self, transcription_id: UUID, data: TranscriptionPatch) -> Transcription:
        values = data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide at least one field to update")
        if any(value is None for field, value in values.items() if field not in {"detected_language", "duration_seconds", "metadata"}):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Required fields cannot be null")
        transcription = await self.get(transcription_id)
        return await self.repository.update(transcription, values)

    async def delete(self, transcription_id: UUID) -> None:
        transcription = await self.get(transcription_id)
        storage_key = transcription.audio_storage_key
        await self.repository.delete(transcription)
        try:
            await asyncio.to_thread(self.audio_storage.remove, storage_key)
        except OSError:
            logger.exception("Unable to remove archived transcription audio", extra={"transcription_id": str(transcription_id)})

    async def delete_many(self, transcription_ids: list[UUID]) -> int:
        deleted = 0
        for transcription_id in dict.fromkeys(transcription_ids):
            transcription = await self.repository.get(transcription_id)
            if transcription is not None:
                await self.delete(transcription_id)
                deleted += 1
        return deleted

    async def store_audio(self, transcription_id: UUID, content: bytes, content_type: str) -> Transcription:
        transcription = await self.get(transcription_id)
        try:
            storage_key, media_type = await asyncio.to_thread(
                self.audio_storage.store, transcription_id, content, content_type
            )
        except AudioStorageError as exc:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

        old_storage_key = transcription.audio_storage_key
        try:
            saved = await self.repository.update(transcription, {
                "audio_storage_key": storage_key,
                "audio_media_type": media_type,
            })
        except Exception:
            await asyncio.to_thread(self.audio_storage.remove, storage_key)
            raise

        if old_storage_key:
            await asyncio.to_thread(self.audio_storage.remove, old_storage_key)
        return saved

    async def audio_file(self, transcription_id: UUID) -> tuple[Path, str]:
        transcription = await self.get(transcription_id)
        if not transcription.audio_storage_key or not transcription.audio_media_type:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio unavailable")
        path = self.audio_storage.path_for(transcription.audio_storage_key)
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio unavailable")
        return path, transcription.audio_media_type
