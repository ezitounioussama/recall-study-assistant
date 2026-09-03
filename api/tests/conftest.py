"""Shared fixtures.

Environment is set before `app` is imported: settings are read once and
cached, so anything set after the first import is ignored.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SESSION_SECRET", "x" * 48)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test-recall.sqlite3"
os.environ["EMBEDDING_PROVIDER"] = "hash"  # no model download to run the suite
# The hash embedder's cosine scores are far lower than nomic's; the product
# threshold would refuse every question in the suite.
os.environ["RETRIEVAL_MIN_SCORE"] = "0.05"

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db import create_all, drop_all  # noqa: E402
from app.main import app  # noqa: E402

GOOD_PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
async def fresh_database():
    """Reset the schema through the engine, not by deleting the file."""
    await drop_all()
    await create_all()
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def register(client: AsyncClient, email: str = "a@b.com", password: str = GOOD_PASSWORD):
    return await client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Tester"},
    )


@pytest.fixture
async def signed_in(client: AsyncClient) -> AsyncClient:
    """A client whose cookie jar already holds a valid session."""
    response = await register(client)
    assert response.status_code == 201
    return client
