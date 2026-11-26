import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.transcript_models import TranscriptionCreate
from app.services.transcript_sessions import SessionStatus, TranscriptionSessionService


class MemoryRepository:
    records = {}

    def __init__(self, session):
        pass

    async def create(self, data: TranscriptionCreate):
        record = SimpleNamespace(
            id=uuid4(),
            title=data.title,
            transcript_text=data.transcript_text,
            detected_language=data.detected_language,
            duration_seconds=data.duration_seconds,
            status=data.status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            transcription_metadata=data.metadata,
        )
        self.records[record.id] = record
        return record

    async def get(self, record_id):
        return self.records.get(record_id)

    async def update(self, record, values):
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
        return record


class FakeSessionFactory:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


@pytest.fixture
def session_service(monkeypatch):
    MemoryRepository.records = {}
    monkeypatch.setattr("app.services.transcript_sessions.TranscriptionRepository", MemoryRepository)
    return TranscriptionSessionService(FakeSessionFactory)


def test_session_lifecycle_and_progress_autosave(session_service):
    async def scenario():
        record = await session_service.create_session("Review", "en")
        assert record.status == SessionStatus.CREATED.value

        await session_service.set_status(record.id, SessionStatus.RECORDING)
        saved = await session_service.save_progress(
            record.id,
            transcript_text="first words",
            detected_language="en",
            duration_seconds=5.0,
            metadata={"segments": [{"text": "first words"}]},
        )
        assert saved.status == SessionStatus.RECORDING.value
        assert saved.transcript_text == "first words"
        assert saved.duration_seconds == 5.0
        assert saved.updated_at >= saved.created_at

        paused = await session_service.save_progress(
            record.id,
            transcript_text="first words",
            detected_language="en",
            duration_seconds=5.0,
            metadata={"manual": True},
            status_value=SessionStatus.PAUSED,
        )
        assert paused.status == SessionStatus.PAUSED.value
        resumed = await session_service.set_status(record.id, SessionStatus.RECORDING)
        assert resumed.status == SessionStatus.RECORDING.value

        completed = await session_service.complete(
            record.id,
            transcript_text="first words completed",
            detected_language="en",
            duration_seconds=11.0,
            metadata={"segments": []},
        )
        assert completed.status == SessionStatus.COMPLETED.value
        assert completed.transcript_text == "first words completed"

    asyncio.run(scenario())


def test_empty_transcript_can_complete_and_interrupted_session_is_failed(session_service):
    async def scenario():
        empty = await session_service.create_session("Silence", None)
        await session_service.set_status(empty.id, SessionStatus.RECORDING)
        completed = await session_service.complete(
            empty.id,
            transcript_text="",
            detected_language=None,
            duration_seconds=2.0,
            metadata={"segments": []},
        )
        assert completed.status == SessionStatus.COMPLETED.value
        assert completed.transcript_text == ""

        interrupted = await session_service.create_session("Interrupted", "hi")
        await session_service.set_status(interrupted.id, SessionStatus.RECORDING)
        failed = await session_service.fail(
            interrupted.id,
            transcript_text="saved partial",
            detected_language="hi",
            duration_seconds=9.0,
            metadata={"segments": [{"text": "saved partial"}]},
        )
        assert failed.status == SessionStatus.FAILED.value
        assert failed.transcript_text == "saved partial"

    asyncio.run(scenario())


def test_invalid_terminal_status_transition_is_rejected(session_service):
    async def scenario():
        completed = await session_service.create_session("Done", "en")
        await session_service.set_status(completed.id, SessionStatus.RECORDING)
        await session_service.complete(
            completed.id,
            transcript_text="done",
            detected_language="en",
            duration_seconds=1,
            metadata={},
        )

        with pytest.raises(HTTPException) as error:
            await session_service.set_status(completed.id, SessionStatus.RECORDING)
        assert error.value.status_code == 409

    asyncio.run(scenario())