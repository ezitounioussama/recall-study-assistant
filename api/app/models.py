"""Tables.

Each table arrives with the pull request that reads it — a table with no reader
is a guess about the future. Auth brought users and sessions; documents and
chunks came with retrieval.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


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

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

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
