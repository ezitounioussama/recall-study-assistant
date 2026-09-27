"""Which parts of the material this student keeps forgetting.

A weak spot is a passage, not a card. Three cards written from the same
paragraph about osmosis are one gap in understanding, and the fix for it is
the paragraph — so cards are grouped by the chunk they came from, and each
group is scored from its review history.

The ranking is a pure function over plain numbers, so it is tested directly.
The query that feeds it is the only part that touches the database.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fsrs import Rating
from app.models import Card, Chunk, Document, ReviewLog


@dataclass
class Evidence:
    """Everything known about one passage's cards."""

    key: str
    reviews: int = 0
    forgotten: int = 0
    retrievabilities: list[float] = field(default_factory=list)
    difficulties: list[float] = field(default_factory=list)

    @property
    def forgotten_rate(self) -> float:
        return self.forgotten / self.reviews if self.reviews else 0.0

    @property
    def recall_now(self) -> float:
        return sum(self.retrievabilities) / len(self.retrievabilities) if self.retrievabilities else 1.0

    @property
    def difficulty(self) -> float:
        return sum(self.difficulties) / len(self.difficulties) if self.difficulties else 0.0


def weakness(e: Evidence) -> float:
    """0 (solid) to 1 (keeps slipping).

    Half the weight is how often it was forgotten — the most direct evidence
    there is. The rest is what FSRS believes now: the chance of recalling it
    this minute, and how difficult the card has proven for this student.
    """
    return round(0.5 * e.forgotten_rate + 0.3 * (1 - e.recall_now) + 0.2 * (e.difficulty / 10), 3)


def is_weak(e: Evidence) -> bool:
    """Reviewed at least once, and either forgotten or fading.

    A passage never reviewed is not weak, it is untested; ranking it would be
    a guess dressed up as a finding.
    """
    return e.reviews > 0 and (e.forgotten > 0 or e.recall_now < 0.85)


def rank(evidence: list[Evidence], limit: int) -> list[Evidence]:
    weak = [e for e in evidence if is_weak(e)]
    return sorted(weak, key=lambda e: (-weakness(e), -e.reviews, e.key))[:limit]


def reason(e: Evidence) -> str:
    if e.forgotten:
        return f"Forgotten {e.forgotten} of {e.reviews} review{'s' if e.reviews != 1 else ''}"
    return f"Recall has faded to {round(e.recall_now * 100)}%"


def excerpt(text: str, limit: int = 220) -> str:
    """The start of a passage, readable as prose.

    Chunks overlap, so most begin mid-sentence; the fragment before the first
    full stop is dropped. Markdown heading marks are removed, since the
    excerpt is shown as plain text.
    """
    text = re.sub(r"#{1,6}\s*", "", text)
    text = " ".join(text.split())
    if text and not text[0].isupper():
        start = re.search(r"[.!?]\s+(?=[A-Z0-9])", text)
        if start and start.end() < len(text) // 2:
            text = text[start.end():]
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


@dataclass
class WeakSpot:
    evidence: Evidence
    chunk: Chunk | None
    document_title: str | None
    cards: list[Card]


async def find(
    db: AsyncSession, *, user_id: str, recall: Callable[[Card], float], limit: int = 3
) -> list[WeakSpot]:
    """This user's weakest passages, with the cards and history behind each.

    `recall` is FSRS's chance of remembering a card right now; the caller owns
    the scheduler and the clock.
    """
    cards = list((await db.scalars(select(Card).where(Card.user_id == user_id))).all())
    if not cards:
        return []

    logs = list((await db.scalars(select(ReviewLog).where(ReviewLog.user_id == user_id))).all())
    by_card: dict[str, list[ReviewLog]] = {}
    for log in logs:
        by_card.setdefault(log.card_id, []).append(log)

    groups: dict[str, Evidence] = {}
    members: dict[str, list[Card]] = {}
    for card in cards:
        # Cards with no passage — written by hand, or whose document was
        # deleted — stand alone rather than being lumped together.
        key = card.chunk_id or f"card:{card.id}"
        e = groups.setdefault(key, Evidence(key=key))
        members.setdefault(key, []).append(card)
        history = by_card.get(card.id, [])
        e.reviews += len(history)
        e.forgotten += sum(1 for log in history if log.rating == Rating.AGAIN)
        if card.stability is not None:
            e.retrievabilities.append(recall(card))
        if card.difficulty is not None:
            e.difficulties.append(card.difficulty)

    top = rank(list(groups.values()), limit)
    chunk_ids = [e.key for e in top if not e.key.startswith("card:")]
    chunks: dict[str, tuple[Chunk, str]] = {}
    if chunk_ids:
        rows = await db.execute(
            select(Chunk, Document.title).join(Document, Document.id == Chunk.document_id).where(Chunk.id.in_(chunk_ids))
        )
        chunks = {chunk.id: (chunk, title) for chunk, title in rows.all()}

    return [
        WeakSpot(
            evidence=e,
            chunk=chunks.get(e.key, (None, None))[0],
            document_title=chunks.get(e.key, (None, None))[1],
            cards=members[e.key],
        )
        for e in top
    ]

