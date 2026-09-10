"""Nearest chunks for a query, scoped to one user.

Brute-force cosine over the user's chunks. A student's library is thousands of
chunks, not millions, and a numpy dot product over a few thousand 768-float
rows is under a millisecond. When that stops being true the storage changes
(sqlite-vec, pgvector) and this function's signature does not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.embeddings import Embedder, unpack
from app.models import Chunk
from app.schemas import Source


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


async def search(
    db: AsyncSession,
    *,
    user_id: str,
    query: np.ndarray,
    k: int = 6,
    min_score: float = 0.0,
    document_ids: list[str] | None = None,
) -> list[Hit]:
    stmt = (
        select(Chunk)
        .where(Chunk.user_id == user_id)
        .options(selectinload(Chunk.document))
    )
    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))

    chunks = list((await db.scalars(stmt)).all())
    if not chunks:
        return []

    matrix = np.stack([unpack(c.embedding) for c in chunks])
    scores = matrix @ query.astype(np.float32)  # vectors are unit-length, so dot = cosine

    order = np.argsort(-scores)[:k]
    return [
        Hit(chunk=chunks[int(i)], score=float(scores[i]))
        for i in order
        if float(scores[i]) >= min_score
    ]


async def find_sources(
    db: AsyncSession,
    embedder: Embedder,
    *,
    user_id: str,
    text: str,
    document_ids: list[str] | None = None,
    k: int | None = None,
    min_score: float | None = None,
) -> list[Source]:
    """Embed a question, search this user's chunks, and number what comes back.

    The numbering is the contract: `Source.index` is what the model cites in
    square brackets and what the client highlights, so it is assigned once,
    here, rather than by each caller.

    Returns detached values, not ORM rows. The chat endpoint needs that — it
    streams, so its database session is closed by the time the answer is
    written — and it costs the other callers nothing.
    """
    cfg = settings()
    query = await embedder.embed_query(text)
    hits = await search(
        db,
        user_id=user_id,
        query=query,
        k=cfg.retrieval_k if k is None else k,
        min_score=cfg.retrieval_min_score if min_score is None else min_score,
        document_ids=document_ids,
    )
    return [
        Source(
            index=i + 1,
            chunk_id=hit.chunk.id,
            document_id=hit.chunk.document_id,
            document_title=hit.chunk.document.title,
            position=hit.chunk.position,
            text=hit.chunk.text,
            score=round(hit.score, 4),
        )
        for i, hit in enumerate(hits)
    ]
