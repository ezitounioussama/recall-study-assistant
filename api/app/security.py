"""Password hashing and session cookies."""

from __future__ import annotations

import datetime as dt

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
