"""Registration, login, logout, and "who am I"."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Session, User
from app.schemas import Credentials, Message, PublicUser, Registration
from app.security import (
    hash_password,
    needs_rehash,
    session_expiry,
    sign_session_id,
    unsign_session_id,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every authentication failure. Saying "no such account" tells
# an attacker which addresses are registered, which turns a login form into an
# account-enumeration oracle.
INVALID = "Email or password is incorrect."


def _set_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=settings().session_cookie_name,
        value=sign_session_id(session_id),
        max_age=settings().session_max_age_seconds,
        # httponly: JavaScript cannot read it, so an XSS bug cannot steal the
        # session. This is the reason the token is not in localStorage.
        httponly=True,
        # lax: the cookie rides top-level navigations but not cross-site POSTs,
        # which covers the common CSRF shapes without breaking ordinary links.
        samesite="lax",
        secure=settings().cookie_secure,
        path="/",
    )


async def current_user(
    session_cookie: str | None = Cookie(default=None, alias="recall_session"),
    db: AsyncSession = Depends(get_session),
) -> User:
    """Dependency for any endpoint that needs a signed-in user."""
    unauthorised = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")

    if not session_cookie:
        raise unauthorised

    session_id = unsign_session_id(session_cookie)
    if session_id is None:
        raise unauthorised

    record = await db.get(Session, session_id)
    if record is None:
        raise unauthorised

    # SQLite hands back a naive datetime, so it is made aware before comparing.
    # Comparing naive to aware raises TypeError, which would surface as a 500
    # on every expired session rather than a 401.
    expires = record.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)

    if expires <= dt.datetime.now(dt.timezone.utc):
        await db.delete(record)
        await db.commit()
        raise unauthorised

    user = await db.get(User, record.user_id)
    if user is None:
        raise unauthorised
    return user


@router.post("/register", response_model=PublicUser, status_code=status.HTTP_201_CREATED)
async def register(
    body: Registration, response: Response, db: AsyncSession = Depends(get_session)
) -> User:
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        # Registration cannot avoid disclosing that an address is taken —
        # the user has to be told why it failed. Login is where the generic
        # message matters.
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered.")

    user = User(
        email=body.email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    session = Session(user_id=user.id, expires_at=session_expiry())
    db.add(session)
    await db.commit()

    _set_cookie(response, session.id)
    return user


@router.post("/login", response_model=PublicUser)
async def login(
    body: Credentials, response: Response, db: AsyncSession = Depends(get_session)
) -> User:
    user = await db.scalar(select(User).where(User.email == body.email))

    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)

    # Opportunistic upgrade: if the stored hash used older parameters, replace
    # it now that the plaintext is in hand. Nobody has to be asked to rotate.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    session = Session(user_id=user.id, expires_at=session_expiry())
    db.add(session)
    await db.commit()

    _set_cookie(response, session.id)
    return user


@router.post("/logout", response_model=Message)
async def logout(
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias="recall_session"),
    db: AsyncSession = Depends(get_session),
) -> Message:
    """End the session server-side, then clear the cookie.

    Deleting the row is the part that matters. Clearing the cookie alone would
    leave a session that still authenticates anyone who kept a copy of it.
    """
    if session_cookie:
        session_id = unsign_session_id(session_cookie)
        if session_id:
            await db.execute(delete(Session).where(Session.id == session_id))
            await db.commit()

    response.delete_cookie(settings().session_cookie_name, path="/")
    return Message(detail="Signed out.")


@router.get("/me", response_model=PublicUser)
async def me(user: User = Depends(current_user)) -> User:
    return user
