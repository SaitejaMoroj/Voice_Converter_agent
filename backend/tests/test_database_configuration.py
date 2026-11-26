import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import normalize_database_url


def test_normalizes_render_postgres_schemes_without_changing_credentials():
    password = "p%40ss%3A%2Fword%3F%23"
    raw_urls = [
        f"postgres://user:{password}@db.example.com:5432/app",
        f"postgresql://user:{password}@db.example.com:5432/app",
        f"postgresql+asyncpg://user:{password}@db.example.com:5432/app",
    ]

    for raw_url in raw_urls:
        normalized = normalize_database_url(raw_url)
        assert normalized.startswith("postgresql+asyncpg://user:")
        assert "db.example.com:5432/app" in normalized
        assert password in normalized


def test_normalizes_psycopg_schemes_to_asyncpg():
    assert normalize_database_url("postgresql+psycopg2://user:pass@host/db") == "postgresql+asyncpg://user:pass@host/db"
    assert normalize_database_url("postgresql+psycopg://user:pass@host/db") == "postgresql+asyncpg://user:pass@host/db"


def test_asyncpg_engine_and_session_factory_initialize():
    url = "postgresql+asyncpg://user:p%40ss@127.0.0.1:5432/app"
    engine = create_async_engine(normalize_database_url(url), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    assert engine.url.drivername == "postgresql+asyncpg"
    assert factory.kw["expire_on_commit"] is False

    asyncio.run(engine.dispose())
