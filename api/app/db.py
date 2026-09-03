"""Database session plumbing."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings().database_url,
    # SQLite's default isolation with aiosqlite is fine for one process. It is
    # a deliberate ceiling: this is a single-user study tool, and swapping the
    # URL for postgres+asyncpg is the only change needed to lift it.
    echo=False,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. One session per request, always closed."""
    async with SessionFactory() as session:
        yield session


async def drop_all() -> None:
    """Drop every table. Used by tests to reset between cases.

    Tests reset the schema through the engine rather than by deleting the
    SQLite file, because unlinking the file leaves the connection pool holding
    handles to a vanished inode — the first version of the suite passed each
    test alone and failed four of them together.
    """
    from app import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


async def create_all() -> None:
    """Create tables from the models.

    Alembic arrives with the first schema change that needs migrating. Doing it
    now would mean maintaining migrations for a schema that is still moving,
    and a migration written before the model settles gets rewritten anyway.
    """
    from app import models  # noqa: F401  — registers the mappers

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
