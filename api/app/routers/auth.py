"""Registration, login, logout, and "who am I".

Two credentials are accepted, for two kinds of client:

* a **session cookie** for the browser — HttpOnly so no script can read it,
  SameSite=Lax against CSRF, and backed by a row so signing out is immediate;
* a **bearer token** for anything without a cookie jar — the n8n automation,
  the MCP tool, curl, Swagger's Authorize button.

Both answer the same question: which user is this? Nothing else in the
application knows or cares which one was used.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Session, User
from app.schemas import Credentials, Message, PublicUser, Registration, TokenOut
from app.security import (
    create_access_token,
    decode_access_token,
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

# auto_error=False: a missing Authorization header is not an error here, it
# just means the caller is a browser and the cookie is checked instead.
# Naming the token URL is what puts the Authorize button in Swagger.
bearer_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)


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
    token: str | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    """Dependency for any endpoint that needs a signed-in user.

    A bearer token wins when both are present: an explicit Authorization
    header is a deliberate act, where a cookie rides along by default.
    """
    unauthorised = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not signed in.", headers={"WWW-Authenticate": "Bearer"}
    )

    if token:
        user_id = decode_access_token(token)
        if user_id is None:
            raise unauthorised
        # The signature proves the token was issued by this service and has not
        # expired. It does not prove the account still exists: a token outlives
        # the user it names, so the row is still looked up.
        bearer_user = await db.get(User, user_id)
        if bearer_user is None:
            raise unauthorised
        return bearer_user

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


@router.post("/token", response_model=TokenOut, summary="Get a bearer token")
async def token(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session),
) -> TokenOut:
    """Exchange an email and password for a bearer token.

    The OAuth2 password flow, so Swagger's Authorize button and every HTTP
    client already know how to use it — the email goes in the `username`
    field. `/auth/login` remains the browser's door; this one is for scripts.
    """
    email = form.username.strip().lower()
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, form.password):
        # The same sentence as /auth/login, for the same reason: a different
        # message for "no such account" turns this into an address checker.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, INVALID, headers={"WWW-Authenticate": "Bearer"}
        )

    return TokenOut(
        access_token=create_access_token(user.id),
        expires_in=settings().access_token_expire_minutes * 60,
    )


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
