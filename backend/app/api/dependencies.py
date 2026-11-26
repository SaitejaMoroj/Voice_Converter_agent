from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.transcript_store import TranscriptionRepository
from app.services.audio_storage_service import AudioStorageService
from app.services.transcript_service import TranscriptService
from app.services.transcript_library import TranscriptionCrudService


def get_transcription_service(session: AsyncSession = Depends(get_session)) -> TranscriptionCrudService:
    return TranscriptionCrudService(TranscriptionRepository(session), AudioStorageService())


def get_transcript_service(session: AsyncSession = Depends(get_session)) -> TranscriptService:
    return TranscriptService(TranscriptionRepository(session))
