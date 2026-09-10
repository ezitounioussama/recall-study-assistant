"""Tables.

Each table arrives with the pull request that reads it — a table with no reader
is a guess about the future. Auth brought users and sessions; documents and
chunks came with retrieval; cards and review logs with the scheduler; study
sessions and generated content with the study history.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    """Creation time, to the microsecond.

    SQLite's CURRENT_TIMESTAMP — what `server_default=func.now()` becomes —
    resolves to whole seconds. Three rows written in the same second then tie,
    and "newest first" falls back to a random uuid, so a list of what you just
    did comes back shuffled. Stamping the time here fixes the order and makes
    it timezone-aware at the same time.
    """
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Stored lowercased. Two accounts differing only in case are the same
    # person to everyone except the database, and the unique index has to agree
    # with that or "email already registered" becomes a coin toss.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)

    display_name: Mapped[str] = mapped_column(String(80))

    # The argon2 hash, which carries its own parameters and salt inside the
    # encoded string. Nothing else about the password is stored.
    password_hash: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    study_sessions: Mapped[list["StudySession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    """A server-side session record.

    The cookie carries only this row's id, signed. Keeping the session in the
    database rather than encoding claims into the cookie means logout is real:
    deleting the row ends the session immediately, where a self-contained token
    stays valid until it expires no matter what the server thinks.
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class Document(Base):
    """One uploaded file, owned by one user.

    The original bytes are not kept. What the product needs is the text and its
    chunks; keeping the upload as well would double the storage for the sake of
    a download button nobody asked for.
    """

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    # Ordered by this in the library, so it needs sub-second resolution.
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Chunk.position",
    )


class Chunk(Base):
    """A passage of a document with its embedding.

    `user_id` is copied from the document on purpose. Retrieval is always
    "search this user's material", and filtering chunks by owner without a join
    keeps the hot path one table. The document row stays the source of truth
    for ownership; this column is an index, not a second opinion.
    """

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True)

    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)

    # float32, little-endian, packed. SQLite has no vector type; storing the
    # raw buffer keeps decoding to one numpy call and avoids a JSON list that
    # would be six times the size.
    embedding: Mapped[bytes] = mapped_column(LargeBinary)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Card(Base):
    """A flashcard and its FSRS memory state.

    `document_id` and `chunk_id` point at where the card came from, so the
    review screen can show the passage. They are nullable and SET NULL on
    delete: removing a document must not erase what you learned from it.
    There is deliberately no ORM relationship to either — the database handles
    the null-out, and the card never needs to walk back to its source in code.
    """

    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )

    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)

    # FSRS state. stability/difficulty are None until the first review.
    state: Mapped[str] = mapped_column(String(12), default="learning")
    step: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    due: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_review: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    reviews: Mapped[list["ReviewLog"]] = relationship(
        back_populates="card", cascade="all, delete-orphan", passive_deletes=True
    )


class ReviewLog(Base):
    """One rating of one card. Append-only.

    The card row holds the current state; this holds how it got there. It is
    what a stats screen reads, and what a future parameter optimiser would
    train on — FSRS weights are fitted to exactly this kind of log.
    """

    __tablename__ = "review_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)

    rating: Mapped[int] = mapped_column(Integer)
    state_before: Mapped[str] = mapped_column(String(12))
    retrievability: Mapped[float] = mapped_column(Float)
    elapsed_seconds: Mapped[float] = mapped_column(Float)
    scheduled_seconds: Mapped[float] = mapped_column(Float)
    stability_after: Mapped[float] = mapped_column(Float)
    difficulty_after: Mapped[float] = mapped_column(Float)
    reviewed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)

    card: Mapped[Card] = relationship(back_populates="reviews")


class StudySession(Base):
    """One thing the student asked the assistant for.

    A session is the unit the history screen lists: a question asked of the
    notes, a summary requested, a quiz generated, a document turned into cards.
    What came back hangs off it as `contents` — usually one row, but a request
    that produced several artefacts keeps them together under one heading.

    `document_id` is SET NULL rather than CASCADE: deleting a document should
    not erase the record that you studied it, the same choice `Card` makes.
    """

    __tablename__ = "study_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # What was asked for: chat, explain, summarise, quiz, flashcards.
    kind: Mapped[str] = mapped_column(String(16), index=True)
    # The question, or the title of the material it was about — whatever makes
    # the row recognisable in a list a week later.
    topic: Mapped[str] = mapped_column(String(300))
    # Which model wrote it. Answers from a 3B and an 8B model are not the same
    # artefact, and a history that hides which one produced this is misleading.
    model: Mapped[str] = mapped_column(String(80), default="")

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    user: Mapped[User] = relationship(back_populates="study_sessions")
    contents: Mapped[list["GeneratedContent"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="GeneratedContent.created_at",
    )


class GeneratedContent(Base):
    """What the model produced, kept as both prose and structure.

    `text` is what a person reads. `data` is the structured payload — the quiz
    questions, the card fronts and backs, the passages cited — so the history
    can re-render an artefact rather than only quote it.

    `user_id` is copied from the session for the same reason `Chunk` copies it:
    every query here is "this user's history", and the ownership filter should
    not need a join. The session row stays the source of truth.
    """

    __tablename__ = "generated_content"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True)

    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    # False when the assistant refused because the material did not cover it.
    # Worth keeping: a history full of refusals is a signal about the library,
    # not about the student.
    grounded: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped[StudySession] = relationship(back_populates="contents")
