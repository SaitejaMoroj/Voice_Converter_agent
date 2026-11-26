import logging
from typing import Annotated, Literal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_transcription_service
from app.core.database import get_session
from app.core.config import get_settings
from app.schemas.transcript_models import (
    TranscriptionCreate,
    TranscriptionBulkDelete,
    TranscriptionBulkDeleteResult,
    TranscriptionPage,
    TranscriptionPatch,
    TranscriptionRead,
    TranscriptionStatistics,
    TranscriptionUpdate,
)
from app.services.transcript_library import TranscriptionCrudService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
SortBy = Literal["created_at", "updated_at", "title", "detected_language", "duration_seconds", "status"]
SortOrder = Literal["asc", "desc"]


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/database", tags=["health"])
async def database_health(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Database health check failed", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable") from exc
    return {"status": "healthy", "database": "connected"}


async def _list_page(
    service: TranscriptionCrudService,
    *,
    page: int,
    page_size: int,
    search: str | None,
    sort_by: SortBy,
    sort_order: SortOrder,
    language: str | None,
    created_after: datetime | None,
    created_before: datetime | None,
) -> TranscriptionPage:
    return await service.list(
        page=page, page_size=page_size, search=search, sort_by=sort_by, sort_order=sort_order,
        language=language, created_after=created_after, created_before=created_before,
    )


@router.get("/transcriptions/search", response_model=TranscriptionPage, tags=["transcriptions"])
async def search_transcriptions(
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
    q: str = Query(min_length=1, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: SortBy = "created_at",
    sort_order: SortOrder = "desc",
    language: str | None = Query(default=None, max_length=32),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> TranscriptionPage:
    return await _list_page(
        service, page=page, page_size=page_size, search=q, sort_by=sort_by, sort_order=sort_order,
        language=language, created_after=created_after, created_before=created_before,
    )


@router.post(
    "/transcriptions",
    response_model=TranscriptionRead,
    status_code=status.HTTP_201_CREATED,
    tags=["transcriptions"],
)
async def create_transcription(
    data: TranscriptionCreate,
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> TranscriptionRead:
    return await service.create(data)


@router.get("/transcriptions", response_model=TranscriptionPage, tags=["transcriptions"])
async def list_transcriptions(
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    sort_by: SortBy = "created_at",
    sort_order: SortOrder = "desc",
    language: str | None = Query(default=None, max_length=32),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> TranscriptionPage:
    return await _list_page(
        service,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        language=language,
        created_after=created_after,
        created_before=created_before,
    )


@router.get("/transcriptions/languages", response_model=list[str], tags=["transcriptions"])
async def list_transcription_languages(
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> list[str]:
    return await service.languages()


@router.get("/transcriptions/stats", response_model=TranscriptionStatistics, tags=["transcriptions"])
async def transcription_statistics(
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> TranscriptionStatistics:
    return TranscriptionStatistics(**await service.statistics())


@router.delete("/transcriptions/bulk", response_model=TranscriptionBulkDeleteResult, tags=["transcriptions"])
async def bulk_delete_transcriptions(
    data: TranscriptionBulkDelete,
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> TranscriptionBulkDeleteResult:
    return TranscriptionBulkDeleteResult(deleted_count=await service.delete_many(data.ids))


@router.get("/transcriptions/{transcription_id}", response_model=TranscriptionRead, tags=["transcriptions"])
async def get_transcription(
    transcription_id: UUID,
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> TranscriptionRead:
    return await service.get(transcription_id)


@router.put("/transcriptions/{transcription_id}/audio", response_model=TranscriptionRead, tags=["transcriptions"])
async def upload_transcription_audio(
    transcription_id: UUID,
    request: Request,
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> TranscriptionRead:
    max_bytes = get_settings().audio_max_upload_bytes
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Audio file is too large.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Audio file is too large.")
        content.extend(chunk)
    content_type = request.headers.get("content-type", "")
    return await service.store_audio(transcription_id, bytes(content), content_type)


@router.get("/transcriptions/{transcription_id}/audio", tags=["transcriptions"])
async def get_transcription_audio(
    transcription_id: UUID,
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
    download: bool = Query(default=False),
) -> FileResponse:
    path, media_type = await service.audio_file(transcription_id)
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type="attachment" if download else "inline",
    )


@router.put("/transcriptions/{transcription_id}", response_model=TranscriptionRead, tags=["transcriptions"])
async def replace_transcription(
    transcription_id: UUID,
    data: TranscriptionUpdate,
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> TranscriptionRead:
    return await service.replace(transcription_id, data)


@router.patch("/transcriptions/{transcription_id}", response_model=TranscriptionRead, tags=["transcriptions"])
async def patch_transcription(
    transcription_id: UUID,
    data: TranscriptionPatch,
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> TranscriptionRead:
    return await service.patch(transcription_id, data)


@router.delete("/transcriptions/{transcription_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["transcriptions"])
async def delete_transcription(
    transcription_id: UUID,
    service: Annotated[TranscriptionCrudService, Depends(get_transcription_service)],
) -> None:
    await service.delete(transcription_id)