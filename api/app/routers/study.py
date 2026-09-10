"""The study history: what this student has generated, and nothing else.

Phase 5 adds the endpoints that create sessions explicitly. Today they are
written by the two flows that already generate content — asking a question and
generating flashcards — and read back here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.routers.auth import current_user
from app.schemas import StudySessionDetail, StudySessionOut
from app.services import study_history

router = APIRouter(prefix="/study", tags=["study"])


@router.get("/history", response_model=list[StudySessionOut], summary="Everything you have generated")
async def history(
    limit: int = Query(default=50, ge=1, le=200),
    kind: str | None = Query(default=None, pattern="^(chat|explain|summarise|quiz|flashcards)$"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> list[StudySessionOut]:
    """Your study sessions, newest first. Never anyone else's."""
    sessions = await study_history.list_sessions(db, user_id=user.id, limit=limit, kind=kind)
    return [StudySessionOut.model_validate(s) for s in sessions]


@router.get("/history/{session_id}", response_model=StudySessionDetail, summary="One session, with what it produced")
async def history_detail(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> StudySessionDetail:
    """One of your sessions and its generated content.

    Someone else's session is a 404, not a 403: confirming that an id exists is
    itself a disclosure, and the client has nothing useful to do with the
    difference.
    """
    session = await study_history.get_session_for(db, user_id=user.id, session_id=session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such study session.")
    return StudySessionDetail.model_validate(session)
