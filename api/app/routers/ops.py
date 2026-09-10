"""The two endpoints that need no sign-in: what this service is, and whether it is up.

Both return typed Pydantic models rather than ad-hoc dicts, so their shape is
in the OpenAPI schema and a client can rely on it.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import __version__

router = APIRouter(tags=["ops"])


class ServiceInfo(BaseModel):
    name: str
    version: str
    description: str
    docs: str = Field(description="Interactive Swagger UI")
    redoc: str = Field(description="Reference documentation")
    health: str
    endpoints: dict[str, str] = Field(description="Route families and what they do")


class Health(BaseModel):
    status: str = Field(description='"ok" when the process can answer requests')
    service: str
    version: str
    time: dt.datetime = Field(description="Server time, UTC")


@router.get("/", response_model=ServiceInfo, summary="What this API is")
async def root() -> ServiceInfo:
    """Service name, version and where to find everything else."""
    return ServiceInfo(
        name="Recall API",
        version=__version__,
        description="Cited answers and spaced repetition from a student's own notes.",
        docs="/docs",
        redoc="/redoc",
        health="/health",
        endpoints={
            "/auth": "register, login, logout, who am I",
            "/documents": "upload, list, inspect, delete and search the user's material",
            "/chat": "streamed, cited answers from that material",
            "/cards": "flashcards, generation and the FSRS review loop",
        },
    )


@router.get("/health", response_model=Health, summary="Liveness")
async def health() -> Health:
    """Liveness. Touches neither the database nor a model, so it stays cheap and honest."""
    return Health(
        status="ok",
        service="recall-api",
        version=__version__,
        time=dt.datetime.now(dt.timezone.utc),
    )
