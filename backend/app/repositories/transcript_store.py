from __future__ import annotations

from typing import Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transcript import Transcription
from app.schemas.transcript_models import TranscriptionCreate


class TranscriptionRepository:
    SORT_COLUMNS = {
        "created_at": Transcription.created_at,
        "updated_at": Transcription.updated_at,
        "title": Transcription.title,
        "detected_language": Transcription.detected_language,
        "duration_seconds": Transcription.duration_seconds,
        "status": Transcription.status,
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        sort_order: str,
        language: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> tuple[list[Transcription], int]:
        statement = select(Transcription)
        count_statement = select(func.count()).select_from(Transcription)
        if search:
            pattern = f"%{search.strip()}%"
            predicate = or_(Transcription.title.ilike(pattern), Transcription.transcript_text.ilike(pattern))
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)
        if language:
            predicate = func.lower(Transcription.detected_language) == language.strip().lower()
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)
        if created_after:
            statement = statement.where(Transcription.created_at >= created_after)
            count_statement = count_statement.where(Transcription.created_at >= created_after)
        if created_before:
            statement = statement.where(Transcription.created_at < created_before)
            count_statement = count_statement.where(Transcription.created_at < created_before)
        column = self.SORT_COLUMNS[sort_by]
        order_expression = column.desc() if sort_order == "desc" else column.asc()
        statement = statement.order_by(order_expression, Transcription.id.asc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        rows = await self.session.scalars(statement)
        total = await self.session.scalar(count_statement)
        return list(rows), total or 0

    async def languages(self) -> list[str]:
        statement = (
            select(Transcription.detected_language)
            .where(Transcription.detected_language.is_not(None))
            .distinct()
            .order_by(Transcription.detected_language.asc())
        )
        values = await self.session.scalars(statement)
        return [value for value in values if value]

    async def statistics(self, month_start: datetime) -> dict[str, int | float]:
        total_sessions = await self.session.scalar(select(func.count()).select_from(Transcription))
        total_duration = await self.session.scalar(
            select(func.coalesce(func.sum(Transcription.duration_seconds), 0.0))
        )
        unique_languages = await self.session.scalar(
            select(func.count(func.distinct(Transcription.detected_language))).where(
                Transcription.detected_language.is_not(None)
            )
        )
        sessions_this_month = await self.session.scalar(
            select(func.count()).select_from(Transcription).where(Transcription.created_at >= month_start)
        )
        return {
            "total_sessions": int(total_sessions or 0),
            "total_duration_seconds": float(total_duration or 0),
            "unique_languages": int(unique_languages or 0),
            "sessions_this_month": int(sessions_this_month or 0),
        }

    async def get(self, transcription_id: UUID) -> Transcription | None:
        return await self.session.get(Transcription, transcription_id)

    async def create(self, data: TranscriptionCreate) -> Transcription:
        values = data.model_dump(exclude={"metadata"})
        values["transcription_metadata"] = data.metadata
        transcription = Transcription(**values)
        self.session.add(transcription)
        await self.session.flush()
        await self.session.refresh(transcription)
        await self._commit()
        return transcription

    async def update(self, transcription: Transcription, values: dict[str, Any]) -> Transcription:
        if "metadata" in values:
            values["transcription_metadata"] = values.pop("metadata")
        for field, value in values.items():
            setattr(transcription, field, value)
        await self.session.flush()
        await self.session.refresh(transcription)
        await self._commit()
        return transcription

    async def delete(self, transcription: Transcription) -> None:
        await self.session.delete(transcription)
        await self._commit()