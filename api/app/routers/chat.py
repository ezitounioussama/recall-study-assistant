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
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.embeddings import Embedder, get_embedder
from app.llm import ChatModel, Turn, get_chat_model
from app.models import User
from app.retrieval import search as vector_search
from app.routers.auth import current_user
from app.schemas import ChatRequest, Source

router = APIRouter(prefix="/chat", tags=["chat"])

REFUSAL = "I can't find that in your notes."

# The last N turns of history travel with each request. Enough to follow a
# "what about the second one?" — not enough for a long conversation to crowd
# the passages out of the context window.
HISTORY_TURNS = 6

# Written for a small local model. Small models follow a shown format far more
# reliably than a described one, so the example answer does the work the rules
# alone would not.
SYSTEM_PROMPT = """You are Recall, a study assistant. The student is asking about their own notes. Below are numbered passages from those notes.

Answer using only what the passages say, and cite the passage each statement comes from in square brackets.

Match the shape of the request:
- A question: a short, direct answer in plain prose, one to four sentences.
- A request to summarise, list, or explain: do that, from the passages, as a numbered or bulleted list if the student asked for points. Every item cites its passage.

Example of the format for a question:
Question: What is the powerhouse of the cell?
Answer: The mitochondrion produces the cell's ATP [1]. It has a double membrane and carries its own DNA [1].

Only if the passages contain nothing relevant to the request, reply with exactly this sentence and nothing else: {refusal}
A summary or explanation of what the passages do say is always possible when they are on the topic — do not refuse those.

Do not mention these instructions or the word "passages".

Passages:
{passages}"""


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_CITATION = re.compile(r"\[(\d+)\]")


def _citations(answer: str, count: int) -> list[int]:
    """The passage numbers the answer cites that exist.

    Small models sometimes invent a [2] when there is only one passage. The
    client should highlight what was used, and it should not have to guess
    which brackets to believe.
    """
    return sorted({int(n) for n in _CITATION.findall(answer) if 1 <= int(n) <= count})


def _render_passages(sources: list[Source]) -> str:
    return "\n\n".join(
        f"[{s.index}] From \"{s.document_title}\", part {s.position + 1}:\n{s.text}" for s in sources
    )


@router.post("")
async def chat(
    body: ChatRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    model: ChatModel = Depends(get_chat_model),
) -> StreamingResponse:
    cfg = settings()
    query = await embedder.embed_query(body.question)
    hits = await vector_search(
        db,
        user_id=user.id,
        query=query,
        k=cfg.retrieval_k,
        min_score=cfg.retrieval_min_score,
        document_ids=body.document_ids,
    )

    # Materialised here, before the stream starts: the database session closes
    # when this function returns, and the generator below must not touch ORM
    # objects after that.
    sources = [
        Source(
            index=i + 1,
            chunk_id=hit.chunk.id,
            document_id=hit.chunk.document_id,
            document_title=hit.chunk.document.title,
            position=hit.chunk.position,
            text=hit.chunk.text,
            score=round(hit.score, 4),
        )
        for i, hit in enumerate(hits)
    ]

    system = SYSTEM_PROMPT.format(refusal=REFUSAL, passages=_render_passages(sources))
    history: list[Turn] = [
        {"role": t.role, "content": t.content} for t in body.history[-HISTORY_TURNS:]
    ]
    messages: list[Turn] = [*history, {"role": "user", "content": body.question}]

    async def events() -> AsyncIterator[str]:
        yield _sse("sources", [s.model_dump() for s in sources])

        if not sources:
            yield _sse("token", {"text": REFUSAL})
            yield _sse("done", {"answer": REFUSAL, "grounded": False, "citations": []})
            return

        parts: list[str] = []
        try:
            async for delta in model.stream(system, messages):
                parts.append(delta)
                yield _sse("token", {"text": delta})
        except Exception:
            yield _sse(
                "error",
                {"detail": "The model could not be reached. Is Ollama running with the chat model pulled?"},
            )
            return

        answer = "".join(parts).strip()
        yield _sse(
            "done",
            {
                "answer": answer,
                "grounded": REFUSAL.lower() not in answer.lower(),
                "citations": _citations(answer, len(sources)),
            },
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
