"""Settings. Every secret comes from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # No default. A signing key with a default is a signing key everyone knows,
    # and every session cookie this service ever issues would be forgeable.
    # Generate one: python -c "import secrets; print(secrets.token_urlsafe(48))"
    session_secret: str = Field(min_length=32)

    database_url: str = "sqlite+aiosqlite:///./recall.sqlite3"

    session_cookie_name: str = "recall_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14  # two weeks

    # False for local http development. True in production — a session cookie
    # sent over plain http is a session cookie anyone on the network has.
    cookie_secure: bool = False

    # The web origin allowed to send credentialed requests. A wildcard is not
    # permitted with credentials by the CORS spec, and browsers enforce it, so
    # this has to be exact.
    web_origin: str = "http://localhost:3100"


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
