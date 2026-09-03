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


# ---- cards and review -------------------------------------------------------


class CardCreate(BaseModel):
    front: str = Field(min_length=1, max_length=2000)
    back: str = Field(min_length=1, max_length=4000)
    document_id: str | None = None
    chunk_id: str | None = None


class GenerateCards(BaseModel):
    document_id: str
    per_chunk: int = Field(default=3, ge=1, le=8)


class CardOut(BaseModel):
    id: str
    document_id: str | None
    chunk_id: str | None
    front: str
    back: str
    state: Literal["learning", "review", "relearning"]
    step: int | None
    stability: float | None
    difficulty: float | None
    due: dt.datetime
    last_review: dt.datetime | None
    reps: int
    lapses: int
    created_at: dt.datetime
    # Probability of recall at the moment of the request, from the memory model.
    retrievability: float


class DueCard(CardOut):
    # Seconds until the card would next be due for each rating — the numbers
    # under the four buttons.
    preview: dict[Literal["again", "hard", "good", "easy"], int]
    # The passage this card was written from, when it still exists.
    source_text: str | None
    source_title: str | None


class ReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=4, description="1 again, 2 hard, 3 good, 4 easy")


class ReviewLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    card_id: str
    rating: int
    state_before: str
    retrievability: float
    elapsed_seconds: float
    scheduled_seconds: float
    stability_after: float
    difficulty_after: float
    reviewed_at: dt.datetime


class ReviewResult(BaseModel):
    card: CardOut
    log: ReviewLogOut


class CardStats(BaseModel):
    total: int
    learning: int
    review: int
    relearning: int
    due_now: int
    reviewed_today: int
    # Share of reviews in the last 30 days that were not "again". None until
    # there is something to measure.
    retention_30d: float | None
    next_due: dt.datetime | None
    # Mean retrievability across the deck right now — "how much of this do I
    # still know" in one number.
    mean_retrievability: float | None
