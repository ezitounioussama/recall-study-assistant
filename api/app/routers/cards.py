"""Flashcards and the review loop.

The scheduler in app/fsrs.py is pure; this module is where it meets the clock
and the database. Every card and every review belongs to the signed-in user,
and another user's card is a 404.
"""

from __future__ import annotations

import datetime as dt
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.fsrs import Memory, Rating, Scheduler, State
from app.llm import ChatModel, get_chat_model
from app.models import Card, Chunk, Document, ReviewLog, User
from app.routers.auth import current_user
from app.schemas import (
    CardCreate,
    CardOut,
    CardStats,
    DueCard,
    GenerateCards,
    ReviewLogOut,
    ReviewRequest,
    ReviewResult,
)

router = APIRouter(prefix="/cards", tags=["cards"])

scheduler = Scheduler()

GENERATE_SYSTEM = """You write flashcards for a student from a passage of their own notes.

Write exactly {n} flashcards. Each card has:
- "front": one specific question that the passage answers
- "back": the answer in one or two sentences, using the passage's own facts

Only ask what the passage actually answers. Prefer why, how, and what-distinguishes questions over trivia. Do not number the cards.

Respond with JSON only, in exactly this shape:
{{"cards": [{{"front": "...", "back": "..."}}]}}"""


# ---- helpers -----------------------------------------------------------------


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    """SQLite hands back naive datetimes; the scheduler compares aware ones."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=dt.timezone.utc)


def _memory(card: Card) -> Memory:
    return Memory(
        state=State(card.state),
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=_aware(card.due),
        last_review=_aware(card.last_review),
    )


def _apply(card: Card, memory: Memory) -> None:
    card.state = memory.state.value
    card.step = memory.step
    card.stability = memory.stability
    card.difficulty = memory.difficulty
    card.due = memory.due  # type: ignore[assignment]
    card.last_review = memory.last_review


def _card_out(card: Card, now: dt.datetime) -> CardOut:
    return CardOut(
        id=card.id,
        document_id=card.document_id,
        chunk_id=card.chunk_id,
        front=card.front,
        back=card.back,
        state=card.state,  # type: ignore[arg-type]
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=_aware(card.due),  # type: ignore[arg-type]
        last_review=_aware(card.last_review),
        reps=card.reps,
        lapses=card.lapses,
        created_at=_aware(card.created_at),  # type: ignore[arg-type]
        retrievability=round(scheduler.retrievability(_memory(card), now), 4),
    )


async def _owned(card_id: str, user: User, db: AsyncSession) -> Card:
    card = await db.scalar(select(Card).where(Card.id == card_id, Card.user_id == user.id))
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such card.")
    return card


async def _owned_document(document_id: str, user: User, db: AsyncSession) -> Document:
    document = await db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
    return document


_JSON_OBJECT = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def parse_cards(text: str) -> list[tuple[str, str]]:
    """Pull (front, back) pairs out of whatever the model returned.

    Accepts {"cards": [...]} or a bare list, tolerates prose around the JSON,
    and drops entries missing either side. Returns [] rather than raising when
    nothing usable is there — the caller decides what an empty result means.
    """
    match = _JSON_OBJECT.search(text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    items = data.get("cards", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []

    pairs: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        front = str(item.get("front", "")).strip()
        back = str(item.get("back", "")).strip()
        if front and back:
            pairs.append((front[:2000], back[:4000]))
    return pairs


# ---- routes ------------------------------------------------------------------
# Static paths first: "/due", "/stats" and "/generate" would otherwise be read
# as card ids by "/{card_id}".


@router.post("", response_model=CardOut, status_code=status.HTTP_201_CREATED)
async def create_card(
    body: CardCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> CardOut:
    if body.document_id is not None:
        await _owned_document(body.document_id, user, db)
    if body.chunk_id is not None:
        chunk = await db.scalar(select(Chunk).where(Chunk.id == body.chunk_id, Chunk.user_id == user.id))
        if chunk is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such chunk.")

    now = _now()
    card = Card(
        user_id=user.id,
        document_id=body.document_id,
        chunk_id=body.chunk_id,
        front=body.front.strip(),
        back=body.back.strip(),
        due=now,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return _card_out(card, now)


@router.post("/generate", response_model=list[CardOut], status_code=status.HTTP_201_CREATED)
async def generate_cards(
    body: GenerateCards,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    model: ChatModel = Depends(get_chat_model),
) -> list[CardOut]:
    """Write cards from every chunk of a document.

    One model call per chunk, bounded by `max_cards_per_generation`. Chunks
    that already have cards are skipped, so calling this twice does not
    double the deck.
    """
    document = await _owned_document(body.document_id, user, db)

    covered = set(
        (await db.scalars(
            select(Card.chunk_id).where(Card.document_id == document.id, Card.chunk_id.is_not(None))
        )).all()
    )
    chunks = list(
        (await db.scalars(
            select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.position)
        )).all()
    )
    pending = [c for c in chunks if c.id not in covered]

    budget = settings().max_cards_per_generation
    now = _now()
    created: list[Card] = []
    for chunk in pending:
        if len(created) >= budget:
            break
        want = min(body.per_chunk, budget - len(created))
        try:
            reply = await model.complete(
                GENERATE_SYSTEM.format(n=want),
                [{"role": "user", "content": chunk.text}],
                json_mode=True,
            )
        except Exception as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "The model could not be reached. Is Ollama running with the chat model pulled?",
            ) from exc

        for front, back in parse_cards(reply)[:want]:
            card = Card(
                user_id=user.id,
                document_id=document.id,
                chunk_id=chunk.id,
                front=front,
                back=back,
                due=now,
            )
            db.add(card)
            created.append(card)

    if pending and not created:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The model returned no usable cards for this document."
        )

    await db.commit()
    for card in created:
        await db.refresh(card)
    return [_card_out(c, now) for c in created]


@router.get("", response_model=list[CardOut])
async def list_cards(
    state: str | None = Query(default=None, pattern="^(learning|review|relearning)$"),
    document_id: str | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> list[CardOut]:
    stmt = select(Card).where(Card.user_id == user.id).order_by(Card.due, Card.created_at)
    if state:
        stmt = stmt.where(Card.state == state)
    if document_id:
        stmt = stmt.where(Card.document_id == document_id)
    now = _now()
    return [_card_out(c, now) for c in (await db.scalars(stmt)).all()]


@router.get("/due", response_model=list[DueCard])
async def due_cards(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> list[DueCard]:
    """Cards to review now, most overdue first, with the four-button preview."""
    now = _now()
    cards = list(
        (await db.scalars(
            select(Card)
            .where(Card.user_id == user.id, Card.due <= now)
            .order_by(Card.due)
            .limit(limit)
        )).all()
    )

    # One query for every source passage rather than one per card.
    chunk_ids = [c.chunk_id for c in cards if c.chunk_id]
    sources: dict[str, tuple[str, str]] = {}
    if chunk_ids:
        rows = await db.execute(
            select(Chunk.id, Chunk.text, Document.title)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_(chunk_ids))
        )
        sources = {chunk_id: (text, title) for chunk_id, text, title in rows.all()}

    out: list[DueCard] = []
    for card in cards:
        memory = _memory(card)
        preview = scheduler.preview(memory, now)
        source = sources.get(card.chunk_id or "")
        out.append(
            DueCard(
                **_card_out(card, now).model_dump(),
                preview={
                    "again": _seconds_until(preview[Rating.AGAIN].due, now),
                    "hard": _seconds_until(preview[Rating.HARD].due, now),
                    "good": _seconds_until(preview[Rating.GOOD].due, now),
                    "easy": _seconds_until(preview[Rating.EASY].due, now),
                },
                source_text=source[0] if source else None,
                source_title=source[1] if source else None,
            )
        )
    return out


def _seconds_until(due: dt.datetime | None, now: dt.datetime) -> int:
    return int((due - now).total_seconds()) if due else 0


@router.get("/stats", response_model=CardStats)
async def stats(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> CardStats:
    now = _now()
    cards = list((await db.scalars(select(Card).where(Card.user_id == user.id))).all())

    by_state = {s.value: 0 for s in State}
    for card in cards:
        by_state[card.state] += 1

    due_now = sum(1 for c in cards if _aware(c.due) <= now)  # type: ignore[operator]
    upcoming = [_aware(c.due) for c in cards if _aware(c.due) > now]  # type: ignore[operator]

    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reviewed_today = await db.scalar(
        select(func.count()).select_from(ReviewLog).where(
            ReviewLog.user_id == user.id, ReviewLog.reviewed_at >= start_of_day
        )
    )

    month_ago = now - dt.timedelta(days=30)
    ratings = list(
        (await db.scalars(
            select(ReviewLog.rating).where(
                ReviewLog.user_id == user.id, ReviewLog.reviewed_at >= month_ago
            )
        )).all()
    )
    retention = (
        round(sum(1 for r in ratings if r > Rating.AGAIN) / len(ratings), 4) if ratings else None
    )

    retrievabilities = [scheduler.retrievability(_memory(c), now) for c in cards if c.stability]
    mean_r = round(sum(retrievabilities) / len(retrievabilities), 4) if retrievabilities else None

    return CardStats(
        total=len(cards),
        learning=by_state["learning"],
        review=by_state["review"],
        relearning=by_state["relearning"],
        due_now=due_now,
        reviewed_today=int(reviewed_today or 0),
        retention_30d=retention,
        next_due=min(upcoming) if upcoming else None,  # type: ignore[type-var]
        mean_retrievability=mean_r,
    )


@router.get("/{card_id}", response_model=CardOut)
async def get_card(
    card_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> CardOut:
    return _card_out(await _owned(card_id, user, db), _now())


@router.post("/{card_id}/review", response_model=ReviewResult)
async def review_card(
    card_id: str,
    body: ReviewRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ReviewResult:
    """Rate a card. The scheduler decides everything else."""
    card = await _owned(card_id, user, db)
    now = _now()
    before = _memory(card)
    rating = Rating(body.rating)

    after = scheduler.review(before, rating, now)
    _apply(card, after)
    card.reps += 1
    if rating == Rating.AGAIN and before.state == State.REVIEW:
        card.lapses += 1

    elapsed = (now - before.last_review).total_seconds() if before.last_review else 0.0
    log = ReviewLog(
        card_id=card.id,
        user_id=user.id,
        rating=int(rating),
        state_before=before.state.value,
        retrievability=round(scheduler.retrievability(before, now), 4),
        elapsed_seconds=round(elapsed, 1),
        scheduled_seconds=_seconds_until(after.due, now),
        stability_after=after.stability or 0.0,
        difficulty_after=after.difficulty or 0.0,
        reviewed_at=now,
    )
    db.add(log)
    await db.commit()
    await db.refresh(card)
    await db.refresh(log)
    return ReviewResult(card=_card_out(card, now), log=ReviewLogOut.model_validate(log))


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    card_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> None:
    card = await _owned(card_id, user, db)
    await db.delete(card)
    await db.commit()
