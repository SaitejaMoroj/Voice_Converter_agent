from enum import StrEnum
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.core.database import SessionFactory
from app.models.transcript import Transcription
from app.repositories.transcript_store import TranscriptionRepository
from app.schemas.transcript_models import TranscriptionCreate


class SessionStatus(StrEnum):
    CREATED = "CREATED"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TRANSITIONS = {
    SessionStatus.CREATED: {SessionStatus.RECORDING, SessionStatus.FAILED},
    SessionStatus.RECORDING: {SessionStatus.PAUSED, SessionStatus.PROCESSING, SessionStatus.COMPLETED, SessionStatus.FAILED},
    SessionStatus.PAUSED: {SessionStatus.RECORDING, SessionStatus.PROCESSING, SessionStatus.COMPLETED, SessionStatus.FAILED},
    SessionStatus.PROCESSING: {SessionStatus.RECORDING, SessionStatus.PAUSED, SessionStatus.COMPLETED, SessionStatus.FAILED},
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: set(),
}


class TranscriptionSessionService:
    def __init__(self, session_factory=SessionFactory) -> None:
        self.session_factory = session_factory

    async def create_session(self, title: str, language: str | None) -> Transcription:
        async with self.session_factory() as session:
            repository = TranscriptionRepository(session)
            return await repository.create(TranscriptionCreate(
                title=title,
                detected_language=language,
                status=SessionStatus.CREATED.value,
            ))

    async def set_status(self, session_id: UUID, next_status: SessionStatus) -> Transcription:
        async with self.session_factory() as session:
            repository = TranscriptionRepository(session)
            current = await self._get(repository, session_id)
            current_status = SessionStatus(current.status)
            self._validate_transition(current_status, next_status)
            return await repository.update(current, {"status": next_status.value})

    async def save_progress(
        self,
        session_id: UUID,
        *,
        transcript_text: str,
        detected_language: str | None,
        duration_seconds: float,
        metadata: dict[str, Any],
        status_value: SessionStatus | None = None,
    ) -> Transcription:
        async with self.session_factory() as session:
            repository = TranscriptionRepository(session)
            current = await self._get(repository, session_id)
            next_status = status_value or SessionStatus(current.status)
            self._validate_transition(SessionStatus(current.status), next_status)
            return await repository.update(current, {
                "transcript_text": transcript_text,
                "detected_language": detected_language,
                "duration_seconds": duration_seconds,
                "transcription_metadata": metadata,
                "status": next_status.value,
            })

    async def complete(
        self,
        session_id: UUID,
        *,
        transcript_text: str,
        detected_language: str | None,
        duration_seconds: float,
        metadata: dict[str, Any],
    ) -> Transcription:
        return await self.save_progress(
            session_id,
            transcript_text=transcript_text,
            detected_language=detected_language,
            duration_seconds=duration_seconds,
            metadata=metadata,
            status_value=SessionStatus.COMPLETED,
        )

    async def fail(
        self,
        session_id: UUID,
        *,
        transcript_text: str,
        detected_language: str | None,
        duration_seconds: float,
        metadata: dict[str, Any],
    ) -> Transcription:
        async with self.session_factory() as session:
            repository = TranscriptionRepository(session)
            current = await self._get(repository, session_id)
            current_status = SessionStatus(current.status)
            if current_status in {SessionStatus.COMPLETED, SessionStatus.FAILED}:
                return current
            self._validate_transition(current_status, SessionStatus.FAILED)
            return await repository.update(current, {
                "transcript_text": transcript_text,
                "detected_language": detected_language,
                "duration_seconds": duration_seconds,
                "transcription_metadata": metadata,
                "status": SessionStatus.FAILED.value,
            })

    @staticmethod
    async def _get(repository: TranscriptionRepository, session_id: UUID) -> Transcription:
        record = await repository.get(session_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcription session not found")
        return record

    @staticmethod
    def _validate_transition(current: SessionStatus, following: SessionStatus) -> None:
        if following != current and following not in TRANSITIONS[current]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot transition a {current.value} session to {following.value}.",
            )