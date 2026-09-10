"""Password hashing, session cookies, and bearer tokens."""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import settings

# argon2id at the library's defaults, which track the RFC 9106 recommendations.
# Left at defaults on purpose: hand-tuned parameters age badly, and the encoded
# hash records whichever ones were used so an upgrade can rehash on next login.
_hasher = PasswordHasher()

_serializer = URLSafeSerializer(settings().session_secret, salt="recall-session")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password.

    Returns False rather than raising, because the caller's job is to answer
    "let them in?" and every failure mode is the same answer. InvalidHashError
    is caught alongside a mismatch so a corrupted row cannot 500 the login
    endpoint — it just fails to authenticate, which is the safe direction.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than the current ones.

    Called after a successful login so hashes upgrade themselves over time
    without asking anyone to change their password.
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def sign_session_id(session_id: str) -> str:
    return _serializer.dumps(session_id)


def unsign_session_id(signed: str) -> str | None:
    """Recover a session id from a cookie, or None if the signature fails.

    The signature is what stops a client editing the cookie to another user's
    session id. Without it the cookie is just a claim.
    """
    try:
        value = _serializer.loads(signed)
    except BadSignature:
        return None
    return value if isinstance(value, str) else None


def session_expiry() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        seconds=settings().session_max_age_seconds
    )


# ---- bearer tokens ---------------------------------------------------------------
#
# Two ways in, for two kinds of client. A browser gets the HttpOnly cookie: it
# cannot be read by JavaScript, so an XSS bug cannot steal it, and signing out
# deletes the server-side row. A script — the n8n automation, the MCP tool,
# curl — gets one of these, because it has no cookie jar and no CSRF surface to
# protect. Both prove the same thing: this request belongs to that user.


def create_access_token(user_id: str, *, expires_minutes: int | None = None) -> str:
    """A signed JWT naming one user, valid for a bounded time."""
    cfg = settings()
    now = dt.datetime.now(dt.timezone.utc)
    minutes = cfg.access_token_expire_minutes if expires_minutes is None else expires_minutes
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + dt.timedelta(minutes=minutes),
        # A unique id per token, so a future revocation list has something to
        # name. Nothing reads it yet; leaving it out later would be a breaking
        # change, putting it in now costs nothing.
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    return jwt.encode(payload, cfg.session_secret, algorithm=cfg.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """The user id inside a token, or None if it cannot be trusted.

    `algorithms` is pinned. Without it a caller could hand over a token whose
    header says `alg: none` and PyJWT would be asked to honour the attacker's
    choice of how to verify the attacker's token. Expiry is checked by the
    library; a token signed with a different secret fails the signature.
    """
    cfg = settings()
    try:
        payload = jwt.decode(token, cfg.session_secret, algorithms=[cfg.jwt_algorithm])
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != "access":
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
