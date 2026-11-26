import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings, normalize_database_url


class Base(DeclarativeBase):
    pass


_database_url = normalize_database_url(get_settings().database_url)
if not _database_url:
    raise RuntimeError("DATABASE_URL is required. Configure it in the environment.")
if _database_url.startswith("sqlite+aiosqlite://"):
    if os.getenv("VOXFLOW_TEST_SQLITE") != "1":
        raise RuntimeError("SQLite is test-only; set DATABASE_URL to a postgresql+asyncpg URL.")
elif "+asyncpg://" not in _database_url:
    raise RuntimeError("DATABASE_URL must use postgresql+asyncpg.")

engine = create_async_engine(_database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
