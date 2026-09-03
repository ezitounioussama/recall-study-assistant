"""Request and response shapes."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalise(cls, value: str) -> str:
        # Lowercased here rather than at the query, so registration and login
        # cannot disagree about whether two spellings are one account.
        return value.strip().lower()


class Registration(Credentials):
    display_name: str = Field(min_length=1, max_length=80)

    # 12 characters, no composition rules. Length is what resists an offline
    # attack; a mandatory symbol mostly produces "Password1!" and a reminder
    # note. NIST 800-63B says the same.
    password: str = Field(min_length=12, max_length=200)


class PublicUser(BaseModel):
    id: str
    email: EmailStr
    display_name: str


class Message(BaseModel):
    detail: str


# ---- documents and retrieval ------------------------------------------------


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    filename: str
    media_type: str
    size_bytes: int
    chunk_count: int
    created_at: dt.datetime


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    text: str
    char_count: int


class DocumentDetail(DocumentOut):
    chunks: list[ChunkOut]


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    position: int
    text: str
    score: float


# ---- chat -------------------------------------------------------------------


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    # Restrict retrieval to these documents. None means the whole library.
    document_ids: list[str] | None = None


class Source(BaseModel):
    """A retrieved passage as the client sees it. `index` is the number the
    answer cites in square brackets."""

    index: int
    chunk_id: str
    document_id: str
    document_title: str
    position: int
    text: str
    score: float
