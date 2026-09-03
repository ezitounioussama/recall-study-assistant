"""Upload, list, inspect, delete — and search across — a user's documents.

Every query here is filtered by the signed-in user. A document that belongs to
someone else is a 404, not a 403: confirming that an id exists is itself a
disclosure.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import get_session
from app.embeddings import Embedder, get_embedder, pack
from app.ingest import UnreadableFile, UnsupportedFile, chunk_text, extract_text, media_type_for
from app.models import Chunk, Document, User
from app.retrieval import search as vector_search
from app.routers.auth import current_user
from app.schemas import DocumentDetail, DocumentOut, SearchHit

router = APIRouter(prefix="/documents", tags=["documents"])


async def _owned(document_id: str, user: User, db: AsyncSession, *, with_chunks: bool = False) -> Document:
    stmt = select(Document).where(Document.id == document_id, Document.user_id == user.id)
    if with_chunks:
        stmt = stmt.options(selectinload(Document.chunks))
    document = await db.scalar(stmt)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document.")
    return document


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
) -> Document:
    filename = file.filename or "upload"
    try:
        media_type = media_type_for(filename)
    except UnsupportedFile as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    data = await file.read()
    if len(data) > settings().max_upload_bytes:
        limit_mb = settings().max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Files are limited to {limit_mb} MB."
        )

    try:
        text = extract_text(filename, data)
    except UnreadableFile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    if not text:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "No text could be read from this file. Scanned PDFs without a text layer are not supported.",
        )

    cfg = settings()
    pieces = chunk_text(text, target=cfg.chunk_chars, overlap=cfg.chunk_overlap_chars)
    vectors = await embedder.embed_documents(pieces)

    document = Document(
        user_id=user.id,
        title=(title or "").strip() or _title_from(filename),
        filename=filename,
        media_type=media_type,
        size_bytes=len(data),
        chunk_count=len(pieces),
    )
    db.add(document)
    await db.flush()

    db.add_all(
        Chunk(
            document_id=document.id,
            user_id=user.id,
            position=i,
            text=piece,
            char_count=len(piece),
            embedding=pack(vector),
        )
        for i, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))
    )
    await db.commit()
    await db.refresh(document)
    return document


def _title_from(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return stem.replace("_", " ").replace("-", " ").strip() or "Untitled"


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> list[Document]:
    stmt = (
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc(), Document.id)
    )
    return list((await db.scalars(stmt)).all())


# Registered before "/{document_id}": routes match in declaration order, and
# the literal "search" would otherwise be read as a document id.
@router.get("/search/", response_model=list[SearchHit], include_in_schema=False)
@router.get("/search", response_model=list[SearchHit])
async def search(
    q: str = Query(min_length=1, max_length=1000),
    k: int = Query(default=6, ge=1, le=20),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
) -> list[SearchHit]:
    query = await embedder.embed_query(q)
    hits = await vector_search(db, user_id=user.id, query=query, k=k)
    return [
        SearchHit(
            chunk_id=hit.chunk.id,
            document_id=hit.chunk.document_id,
            document_title=hit.chunk.document.title,
            position=hit.chunk.position,
            text=hit.chunk.text,
            score=round(hit.score, 4),
        )
        for hit in hits
    ]


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> Document:
    return await _owned(document_id, user, db, with_chunks=True)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> None:
    document = await _owned(document_id, user, db)
    await db.delete(document)  # chunks go with it: cascade="all, delete-orphan"
    await db.commit()
