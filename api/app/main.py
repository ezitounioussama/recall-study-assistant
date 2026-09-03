"""The Recall API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import create_all
from app.routers import auth, documents


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    yield


app = FastAPI(
    title="Recall API",
    version="0.3.0",
    description="Auth, documents and retrieval; chat and the FSRS scheduler next.",
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

app.include_router(auth.router)
app.include_router(documents.router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness. Touches nothing, so it stays honest about being cheap."""
    return {"status": "ok"}
