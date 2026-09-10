"""The four study features, and the history they write.

Every endpoint here does the same four things: find the passages in this
student's own material, ask the AI service for one kind of study content,
save what came back, and return it with the id of the row it was saved as.

Retrieval comes first on purpose. It decides whether the model is asked at
all — material that does not cover the topic produces a refusal, not an
invented answer — and it is what scopes everything to one user: the search
only ever sees chunks whose owner is the caller.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.embeddings import Embedder, get_embedder
from app.models import Card, StudySession, User
from app.retrieval import find_sources
from app.routers.auth import current_user
from app.routers.cards import card_out
from app.schemas import (
    ExplainRequest,
    ExplainResponse,
    FlashcardsRequest,
    FlashcardsResponse,
    QuizRequest,
    QuizResponse,
    Source,
    StudyRequest,
    StudySessionDetail,
    StudySessionOut,
    SummariseRequest,
    SummariseResponse,
)
from app.services import study_history
from app.services.ai_service import AiService, AiUnavailable, get_ai_service
from app.services.study_history import Artefact, Recording

router = APIRouter(prefix="/study", tags=["study"])

# What to say when the library has nothing on the topic and an empty result
# would be useless to the caller.
NOTHING_FOUND = (
    "Nothing in your material covers that closely enough. Upload something on the topic, "
    "or ask about something your notes already contain."
)


# ---- the shape every study endpoint shares -------------------------------------


async def _passages(
    body: StudyRequest, user: User, db: AsyncSession, embedder: Embedder
) -> list[Source]:
    """The passages this request will be answered from. Only ever this user's."""
    return await find_sources(
        db, embedder, user_id=user.id, text=body.topic, document_ids=body.document_ids
    )


async def _save(
    db: AsyncSession,
    *,
    user: User,
    kind: str,
    topic: str,
    artefact: Artefact,
    sources: list[Source],
) -> StudySession:
    """Record one generation, and note which document it came from.

    A session is linked to a document only when every passage came from the
    same one. "This session was about that document" is either true or it is
    noise, and a link to the first of three would be noise.
    """
    documents = {s.document_id for s in sources}
    return await study_history.record(
        db,
        Recording(
            user_id=user.id,
            kind=kind,
            topic=topic,
            model=settings().chat_model,
            document_id=documents.pop() if len(documents) == 1 else None,
            artefacts=[artefact],
        ),
    )


def _unavailable(exc: AiUnavailable) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, exc.detail)


def _nothing_found() -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOTHING_FOUND)


# ---- 1. explain -------------------------------------------------------------------


@router.post("/explain", response_model=ExplainResponse, summary="Explain a topic from your notes")
async def explain(
    body: ExplainRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    ai: AiService = Depends(get_ai_service),
) -> ExplainResponse:
    """A short, cited explanation, or an honest refusal.

    A refusal is a 200 with `grounded: false`, not an error: "your notes do
    not cover this" is a true and useful answer to "explain X", and it is
    saved to the history like any other.
    """
    sources = await _passages(body, user, db, embedder)
    try:
        explanation = await ai.explain(body.topic, sources, level=body.level)
    except AiUnavailable as exc:
        raise _unavailable(exc) from exc

    session = await _save(
        db,
        user=user,
        kind="explain",
        topic=body.topic,
        sources=sources,
        artefact=Artefact(
            kind="explanation",
            text=explanation.text,
            data={"citations": explanation.citations, "level": body.level},
            grounded=explanation.grounded,
        ),
    )
    return ExplainResponse(
        session_id=session.id,
        kind="explain",
        topic=body.topic,
        model=settings().chat_model,
        created_at=_aware(session.created_at),
        sources=sources,
        explanation=explanation,
    )


# ---- 2. summarise -----------------------------------------------------------------


@router.post("/summarise", response_model=SummariseResponse, summary="Summarise your material on a topic")
async def summarise(
    body: SummariseRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    ai: AiService = Depends(get_ai_service),
) -> SummariseResponse:
    """At most `points` cited sentences. Fewer when the material supports fewer."""
    sources = await _passages(body, user, db, embedder)
    try:
        summary = await ai.summarise(sources, title=body.topic, points=body.points)
    except AiUnavailable as exc:
        raise _unavailable(exc) from exc

    session = await _save(
        db,
        user=user,
        kind="summarise",
        topic=body.topic,
        sources=sources,
        artefact=Artefact(
            kind="summary",
            text="\n".join(f"- {p}" for p in summary.points),
            data={"title": summary.title, "points": summary.points, "citations": summary.citations},
            grounded=summary.grounded,
        ),
    )
    return SummariseResponse(
        session_id=session.id,
        kind="summarise",
        topic=body.topic,
        model=settings().chat_model,
        created_at=_aware(session.created_at),
        sources=sources,
        summary=summary,
    )


# ---- 3. quiz ----------------------------------------------------------------------


@router.post("/quiz", response_model=QuizResponse, summary="Multiple-choice questions from your notes")
async def quiz(
    body: QuizRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    ai: AiService = Depends(get_ai_service),
) -> QuizResponse:
    """Questions the passages actually answer, with the correct choice marked.

    Unlike `/explain`, nothing to quiz on is a 422 rather than an empty 200:
    the caller asked for N questions and has nothing to render without them.
    """
    sources = await _passages(body, user, db, embedder)
    if not sources:
        raise _nothing_found()

    try:
        generated = await ai.generate_quiz(
            sources, count=body.count, difficulty=body.difficulty, topic=body.topic
        )
    except AiUnavailable as exc:
        raise _unavailable(exc) from exc

    if not generated.questions:
        # The model was asked and produced nothing usable — every question it
        # wrote failed validation. Saying so beats returning an empty quiz.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The model did not return a usable question. Try again, or a narrower topic.",
        )

    session = await _save(
        db,
        user=user,
        kind="quiz",
        topic=body.topic,
        sources=sources,
        artefact=Artefact(
            kind="quiz",
            text=f"{len(generated.questions)} questions on {body.topic}",
            data=generated.model_dump(mode="json"),
        ),
    )
    return QuizResponse(
        session_id=session.id,
        kind="quiz",
        topic=body.topic,
        model=settings().chat_model,
        created_at=_aware(session.created_at),
        sources=sources,
        quiz=generated,
    )


# ---- 4. flashcards ------------------------------------------------------------------


@router.post(
    "/flashcards",
    response_model=FlashcardsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Write flashcards on a topic and schedule them",
)
async def flashcards(
    body: FlashcardsRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    ai: AiService = Depends(get_ai_service),
) -> FlashcardsResponse:
    """Cards written from the passages that match a topic, saved and due now.

    `/cards/generate` covers a whole document, passage by passage. This is the
    topic-shaped door into the same deck: ask for five cards on scheduling and
    get five, drawn from wherever scheduling is discussed. The cards are real
    rows, so they enter the FSRS schedule immediately.
    """
    sources = await _passages(body, user, db, embedder)
    if not sources:
        raise _nothing_found()

    # Spread the request across the passages found, best match first, so a
    # request for three cards does not take all three from one paragraph.
    per_passage = max(1, -(-body.count // len(sources)))
    now = dt.datetime.now(dt.timezone.utc)
    created: list[Card] = []
    for source in sources:
        if len(created) >= body.count:
            break
        try:
            drafts = await ai.generate_flashcards(source.text, count=min(per_passage, body.count - len(created)))
        except AiUnavailable as exc:
            raise _unavailable(exc) from exc

        for draft in drafts:
            card = Card(
                user_id=user.id,
                document_id=source.document_id,
                chunk_id=source.chunk_id,
                front=draft.front,
                back=draft.back,
                due=now,
            )
            db.add(card)
            created.append(card)

    if not created:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The model did not return a usable card. Try again, or a narrower topic.",
        )

    await db.flush()
    for card in created:
        await db.refresh(card)

    session = await _save(
        db,
        user=user,
        kind="flashcards",
        topic=body.topic,
        sources=sources,
        artefact=Artefact(
            kind="flashcards",
            text=f"{len(created)} cards on {body.topic}",
            data=[{"id": c.id, "front": c.front, "back": c.back, "chunk_id": c.chunk_id} for c in created],
        ),
    )
    return FlashcardsResponse(
        session_id=session.id,
        kind="flashcards",
        topic=body.topic,
        model=settings().chat_model,
        created_at=_aware(session.created_at),
        sources=sources,
        cards=[card_out(c, now) for c in created],
    )


def _aware(value: dt.datetime) -> dt.datetime:
    """SQLite hands back naive datetimes; the API promises timezone-aware ones."""
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


# ---- history ------------------------------------------------------------------------


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
