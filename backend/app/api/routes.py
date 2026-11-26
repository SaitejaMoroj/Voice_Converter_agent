from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import text

from app.api.dependencies import get_transcript_service
from app.core.database import get_session
from app.schemas.transcript import TranscriptCreate, TranscriptList, TranscriptRead
from app.services.transcript_service import TranscriptService

router = APIRouter(prefix="/api/v1")


@router.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready", tags=["health"])
async def readiness(session=Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/transcripts", response_model=TranscriptList, tags=["transcripts"])
async def list_transcripts(service: Annotated[TranscriptService, Depends(get_transcript_service)], limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)) -> TranscriptList:
    items, total = await service.list(limit, offset)
    return TranscriptList(items=[_legacy_transcript(item) for item in items], total=total)


@router.post("/transcripts", response_model=TranscriptRead, status_code=status.HTTP_201_CREATED, tags=["transcripts"])
async def create_transcript(data: TranscriptCreate, service: Annotated[TranscriptService, Depends(get_transcript_service)]) -> TranscriptRead:
    return _legacy_transcript(await service.create(data))


@router.get("/transcripts/{transcript_id}", response_model=TranscriptRead, tags=["transcripts"])
async def get_transcript(transcript_id: UUID, service: Annotated[TranscriptService, Depends(get_transcript_service)]) -> TranscriptRead:
    return _legacy_transcript(await service.get(transcript_id))


@router.delete("/transcripts/{transcript_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["transcripts"])
async def delete_transcript(transcript_id: UUID, service: Annotated[TranscriptService, Depends(get_transcript_service)]) -> Response:
    await service.delete(transcript_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _legacy_transcript(item) -> TranscriptRead:
    return TranscriptRead(
        id=item.id,
        title=item.title,
        content=item.transcript_text,
        language=item.detected_language or "auto",
        duration_seconds=round(item.duration_seconds or 0),
        created_at=item.created_at,
    )
