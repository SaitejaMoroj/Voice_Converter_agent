import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

from app.core.database import Base, get_session
from app.main import app
from app.models import Transcription


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "voxflow-test.db"
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}", poolclass=NullPool
    )
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def create_schema():
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())

    async def override_session():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    asyncio.run(test_engine.dispose())
