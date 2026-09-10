"""The Recall API.

Run:   uvicorn app.main:app --port 8100
Docs:  http://localhost:8100/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings
from app.db import create_all
from app.routers import auth, cards, chat, documents, ops, study


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    yield


app = FastAPI(
    title="Recall API",
    version=__version__,
    description=(
        "Cited answers and spaced repetition from a student's own notes. "
        "Upload material, ask questions answered only from it with citations, "
        "generate flashcards, and review them on an FSRS schedule. "
        "Every route except `/`, `/health`, `/auth/register`, `/auth/login` and `/auth/token` needs a credential: the session cookie a browser gets from `/auth/login`, or a bearer token from `/auth/token`."
    ),
    contact={"name": "Oussama Ezitouni", "url": "https://github.com/ezitounioussama/recall-study-assistant"},
    lifespan=lifespan,
)

# allow_credentials with an exact origin, never a wildcard: the CORS spec
# forbids "*" alongside credentials and browsers enforce it, so a wildcard here
# would silently break every cookie-bearing request from the web app.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ops.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(cards.router)
app.include_router(study.router)
