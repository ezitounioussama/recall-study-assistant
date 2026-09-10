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


class TokenOut(BaseModel):
    """An OAuth2 password-flow response, which is what Swagger's Authorize expects."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the token stops being accepted")


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


# ---- AI service output ---------------------------------------------------------
#
# What app/services/ai_service.py returns. Pydantic models rather than free
# text, so a route can hand one straight back and its shape is in the OpenAPI
# schema. `citations` and `source_index` refer to `Source.index`, the number
# the client shows beside each passage.


class Explanation(BaseModel):
    topic: str
    text: str
    grounded: bool = Field(description="False when the material did not support an answer")
    citations: list[int] = Field(default_factory=list)


class Summary(BaseModel):
    title: str
    points: list[str] = Field(default_factory=list, description="One sentence each, ending in its citation")
    grounded: bool = True
    citations: list[int] = Field(default_factory=list)


class QuizQuestion(BaseModel):
    question: str
    choices: list[str] = Field(min_length=2)
    answer_index: int = Field(ge=0, description="Index into `choices`")
    explanation: str = ""
    source_index: int | None = Field(default=None, description="The passage this question came from")


class QuizOut(BaseModel):
    topic: str
    difficulty: str
    questions: list[QuizQuestion] = Field(default_factory=list)


class FlashcardDraft(BaseModel):
    """A card before it is saved and scheduled."""

    front: str
    back: str


class ChecklistItem(BaseModel):
    """One thing to do, and what it proves."""

    step: str = Field(description="An action: recall, explain, work through, compare")
    why: str = Field(default="", description="What this step tests")
    source_index: int | None = Field(default=None, description="The passage it came from")


class ChecklistOut(BaseModel):
    topic: str
    items: list[ChecklistItem] = Field(default_factory=list)


# ---- study history ---------------------------------------------------------------


class GeneratedContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    text: str
    data: dict | list | None = None
    grounded: bool
    created_at: dt.datetime


class StudySessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    topic: str
    document_id: str | None
    model: str
    created_at: dt.datetime


class StudySessionDetail(StudySessionOut):
    contents: list[GeneratedContentOut]


# ---- study endpoints -------------------------------------------------------------
#
# One request shape, four variations. `topic` is both the thing to explain and
# the query used to find the passages, which is why it has a floor: "a" would
# retrieve noise, and asking a model to explain it would waste a minute of CPU.


Level = Literal["beginner", "intermediate", "advanced"]


class StudyRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=500, description="What to study. Also the retrieval query.")
    document_ids: list[str] | None = Field(
        default=None, max_length=20, description="Restrict to these documents. Omit for the whole library."
    )

    @field_validator("topic")
    @classmethod
    def not_only_whitespace(cls, value: str) -> str:
        topic = value.strip()
        if len(topic) < 3:
            raise ValueError("topic must be at least 3 characters")
        return topic


class ExplainRequest(StudyRequest):
    level: Level = "beginner"


class SummariseRequest(StudyRequest):
    points: int = Field(default=5, ge=1, le=12, description="At most this many points; fewer if the material is thin")


class QuizRequest(StudyRequest):
    count: int = Field(default=5, ge=1, le=20)
    difficulty: Level = "beginner"


class FlashcardsRequest(StudyRequest):
    count: int = Field(default=5, ge=1, le=20, description="Cards to write, spread across the passages found")


class ChecklistRequest(StudyRequest):
    items: int = Field(default=6, ge=1, le=12, description="Steps to produce; fewer if the material is thin")


class StudyResponse(BaseModel):
    """What every study endpoint returns around its payload.

    `session_id` is the history row this generation was saved as, so a client
    can link straight to it rather than searching the list for what it just did.
    """

    session_id: str
    kind: str
    topic: str
    model: str
    created_at: dt.datetime
    sources: list[Source]


class ExplainResponse(StudyResponse):
    explanation: Explanation


class SummariseResponse(StudyResponse):
    summary: Summary


class QuizResponse(StudyResponse):
    quiz: QuizOut


class FlashcardsResponse(StudyResponse):
    cards: list[CardOut] = Field(description="Saved and due now, so they appear in the next review session")


class ChecklistResponse(StudyResponse):
    checklist: ChecklistOut
