"""Settings. Every secret comes from the environment."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

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

    # ---- documents and retrieval ------------------------------------------

    # "ollama" talks to a local Ollama server. "hash" is a deterministic
    # bag-of-words embedder with no model behind it: it exists so the test
    # suite runs anywhere, and it is not good enough to ship.
    embedding_provider: Literal["ollama", "hash"] = "ollama"
    ollama_host: str = "http://127.0.0.1:11434"
    embedding_model: str = "nomic-embed-text"

    # ~1800 characters is roughly 450 tokens: large enough that a chunk carries
    # a whole idea, small enough that a citation points somewhere specific.
    chunk_chars: int = 1800
    chunk_overlap_chars: int = 200

    max_upload_bytes: int = 10 * 1024 * 1024

    # ---- chat ---------------------------------------------------------------

    # llama3.2:3b answers in seconds on a CPU. qwen3:8b is noticeably better
    # and noticeably slower; it also emits a reasoning block, which the adapter
    # switches off. Either is a settings change.
    chat_model: str = "llama3.2:3b"

    # Passages scoring under this are not shown to the model, and a question
    # that retrieves none gets the fixed refusal. Calibrated on nomic-embed-text
    # cosine: relevant passages land at 0.8+, unrelated ones at 0.4-0.57.
    retrieval_min_score: float = 0.6
    retrieval_k: int = 5

    # ---- cards --------------------------------------------------------------

    cards_per_chunk: int = 3
    # One generation call is bounded so a 300-page upload cannot turn into an
    # hour of model time from a single click.
    max_cards_per_generation: int = 60


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
