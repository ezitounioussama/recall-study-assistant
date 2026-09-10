"""Ask a question of your own notes, and get the answer as it is written.

The response is a server-sent event stream:

    event: sources   the passages retrieved, numbered — sent first, so the UI
                     can show what the answer will be grounded in before a
                     single token arrives
    event: token     a text delta
    event: done      the full answer and whether it was grounded
    event: error     the model could not be reached; the stream ends

If nothing in the user's material clears the similarity threshold, no model
is called at all: the reply is a fixed refusal and `grounded` is false. A
refusal decided by retrieval is deterministic; one left to the model is a
coin toss dressed up as a policy.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.embeddings import Embedder, get_embedder
from app.llm import Turn
from app.models import User
from app.retrieval import find_sources
from app.routers.auth import current_user
from app.schemas import ChatRequest, Source

# The prompt, the refusal and the citation check live in the AI service, so
# this router only moves data: retrieve, hand over, relay.
from app.services.study_history import Artefact, Recording, record_detached
from app.services.ai_service import (  # noqa: E402 - grouped with the app imports on purpose
    HISTORY_TURNS,
    REFUSAL,
    AiService,
    AiUnavailable,
    get_ai_service,
)

router = APIRouter(prefix="/chat", tags=["chat"])

def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(
    body: ChatRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    ai: AiService = Depends(get_ai_service),
) -> StreamingResponse:
    cfg = settings()
    # Follow-ups lean on the previous turn: "and how is that different from
    # CFS?" embeds to almost nothing on its own and retrieved the wrong chunk
    # in testing. Folding the last user question into the retrieval query
    # keeps the topic; the model still sees only the current question.
    previous = next((t.content for t in reversed(body.history) if t.role == "user"), None)
    retrieval_text = f"{previous}\n{body.question}" if previous else body.question

    # Materialised before the stream starts: the database session closes when
    # this function returns, and the generator below must not touch ORM
    # objects after that. find_sources returns detached values for that reason.
    sources = await find_sources(
        db, embedder, user_id=user.id, text=retrieval_text, document_ids=body.document_ids
    )

    history: list[Turn] = [{"role": t.role, "content": t.content} for t in body.history]

    async def events() -> AsyncIterator[str]:
        yield _sse("sources", [s.model_dump() for s in sources])

        if not sources:
            yield _sse("token", {"text": REFUSAL})
            yield _sse("done", {"answer": REFUSAL, "grounded": False, "citations": []})
            # A refusal is history too: a run of them says the library is thin
            # on a topic, which is worth being able to see.
            await _remember(REFUSAL, grounded=False, citations=[])
            return

        parts: list[str] = []
        try:
            async for delta in ai.stream_answer(body.question, sources, history):
                parts.append(delta)
                yield _sse("token", {"text": delta})
        except AiUnavailable as exc:
            # The stream has already started, so a 502 is no longer possible:
            # the failure has to arrive as an event the client can render.
            yield _sse("error", {"detail": exc.detail})
            return

        answer = "".join(parts).strip()
        grounded = REFUSAL.lower() not in answer.lower()
        citations = AiService.citations(answer, len(sources))
        yield _sse("done", {"answer": answer, "grounded": grounded, "citations": citations})
        await _remember(answer, grounded=grounded, citations=citations)

    async def _remember(answer: str, *, grounded: bool, citations: list[int]) -> None:
        """Save the answer to the study history.

        Detached, because FastAPI closed this handler's database session when
        it returned the StreamingResponse — the generator above runs after
        that. The passages are stored by reference rather than in full: the
        chunk rows already hold the text, and copying five of them into every
        history entry would grow the database faster than the library does.
        """
        await record_detached(
            Recording(
                user_id=user.id,
                kind="chat",
                topic=body.question,
                model=cfg.chat_model,
                document_id=body.document_ids[0] if body.document_ids and len(body.document_ids) == 1 else None,
                artefacts=[
                    Artefact(
                        kind="answer",
                        text=answer,
                        data={
                            "citations": citations,
                            "sources": [
                                {
                                    "index": s.index,
                                    "chunk_id": s.chunk_id,
                                    "document_id": s.document_id,
                                    "document_title": s.document_title,
                                    "position": s.position,
                                    "score": s.score,
                                }
                                for s in sources
                            ],
                        },
                        grounded=grounded,
                    )
                ],
            )
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tells nginx-style proxies not to buffer, or "streaming" arrives
            # as one lump at the end.
            "X-Accel-Buffering": "no",
        },
    )
