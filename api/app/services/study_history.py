"""Writing to the study history, and reading it back safely.

Every AI result the student receives is worth keeping: it is what "what did I
study last week" means, and it is the only record of what the assistant
actually said. One function writes a session with its contents; the readers
take a user and can only ever see that user's rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import SessionFactory
from app.models import GeneratedContent, StudySession

log = logging.getLogger(__name__)


@dataclass
class Artefact:
    """One thing the model produced, on its way into the history."""

    kind: str
    text: str = ""
    data: Any = None
    grounded: bool = True


@dataclass
class Recording:
    """A study session about to be written."""

    user_id: str
    kind: str
    topic: str
    artefacts: list[Artefact] = field(default_factory=list)
    document_id: str | None = None
    model: str = ""


async def record(db: AsyncSession, entry: Recording) -> StudySession:
    """Save a session and its contents. Returns the session, flushed."""
    session = StudySession(
        user_id=entry.user_id,
        document_id=entry.document_id,
        kind=entry.kind,
        topic=entry.topic[:300],
        model=entry.model,
    )
    db.add(session)
    await db.flush()

    db.add_all(
        GeneratedContent(
            session_id=session.id,
            user_id=entry.user_id,
            kind=a.kind,
            text=a.text,
            data=a.data,
            grounded=a.grounded,
        )
        for a in entry.artefacts
    )
    await db.commit()
    await db.refresh(session)
    return session


async def record_detached(entry: Recording) -> None:
    """Save from somewhere that no longer has a request's session.

    The chat endpoint streams: by the time the answer is complete, FastAPI has
    closed the session the handler was given. This opens its own.

    Failures are logged, not raised. A history row that could not be written is
    a real problem, but it is not worth turning an answer the student already
    read into an error.
    """
    try:
        async with SessionFactory() as db:
            await record(db, entry)
    except Exception:  # noqa: BLE001 - a background write must not escape
        log.exception("could not record study session for user %s", entry.user_id)


async def list_sessions(db: AsyncSession, *, user_id: str, limit: int = 50, kind: str | None = None) -> list[StudySession]:
    """Newest first, and only this user's."""
    stmt = (
        select(StudySession)
        .where(StudySession.user_id == user_id)
        .order_by(StudySession.created_at.desc(), StudySession.id)
        .limit(limit)
    )
    if kind:
        stmt = stmt.where(StudySession.kind == kind)
    return list((await db.scalars(stmt)).all())


async def get_session_for(db: AsyncSession, *, user_id: str, session_id: str) -> StudySession | None:
    """One session with its contents, or None if it is not this user's.

    The owner is part of the query rather than checked afterwards. A filter
    that has to be remembered eventually is not, and "load it, then compare
    the owner" is the shape that leaks other people's data when someone adds
    an early return.
    """
    return await db.scalar(
        select(StudySession)
        .where(StudySession.id == session_id, StudySession.user_id == user_id)
        .options(selectinload(StudySession.contents))
    )
