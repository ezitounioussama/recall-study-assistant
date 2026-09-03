"""Tables.

Only what auth needs. Documents, chunks, cards and reviews arrive with the pull
requests that use them — a table with no reader is a guess about the future.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
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
