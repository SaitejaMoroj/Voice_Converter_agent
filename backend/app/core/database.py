import logging
import os
from collections.abc import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings, normalize_database_url

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_database_url = normalize_database_url(get_settings().database_url)
engine: AsyncEngine | None = None
SessionFactory: async_sessionmaker[AsyncSession] | None = None

if not _database_url:
    logger.warning("DATABASE_URL is not configured; database-backed endpoints will return 503")
else:
    if _database_url.startswith("sqlite+aiosqlite://"):
        if os.getenv("VOXFLOW_TEST_SQLITE") != "1":
            logger.warning("SQLite is test-only and is ignored outside tests")
        else:
            try:
                engine = create_async_engine(_database_url, pool_pre_ping=True)
                SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
            except Exception:
                logger.exception("Unable to initialize the test SQLite database")
    elif "+asyncpg://" in _database_url:
        try:
            engine = create_async_engine(_database_url, pool_pre_ping=True)
            SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
        except Exception:
            logger.exception("Unable to initialize the PostgreSQL database engine")
    else:
        logger.warning("DATABASE_URL must use postgresql+asyncpg or sqlite+aiosqlite for tests")


async def get_session() -> AsyncIterator[AsyncSession]:
    if engine is None or SessionFactory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable. Configure DATABASE_URL and apply migrations.",
        )

    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
