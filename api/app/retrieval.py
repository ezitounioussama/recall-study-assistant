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

from app.embeddings import unpack
from app.models import Chunk


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
