"""The public surface: GET /, GET /health, and the generated documentation.

None of these may require a sign-in, and their shapes are part of the contract.
"""

from __future__ import annotations

import datetime as dt

from app import __version__


class TestRoot:
    async def test_describes_the_service(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Recall API"
        assert body["version"] == __version__
        assert body["docs"] == "/docs"
        assert set(body["endpoints"]) == {"/auth", "/documents", "/chat", "/cards"}

    async def test_needs_no_cookie(self, client):
        client.cookies.clear()
        assert (await client.get("/")).status_code == 200


class TestHealth:
    async def test_is_structured_and_current(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "recall-api"
        assert body["version"] == __version__
        reported = dt.datetime.fromisoformat(body["time"])
        assert abs((dt.datetime.now(dt.timezone.utc) - reported).total_seconds()) < 5

    async def test_needs_no_cookie(self, client):
        client.cookies.clear()
        assert (await client.get("/health")).status_code == 200


class TestDocumentation:
    async def test_swagger_ui_is_served(self, client):
        response = await client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()

    async def test_openapi_schema_carries_the_metadata(self, client):
        schema = (await client.get("/openapi.json")).json()
        assert schema["info"]["title"] == "Recall API"
        assert schema["info"]["version"] == __version__
        assert "cited" in schema["info"]["description"].lower()
        assert {"/", "/health"} <= set(schema["paths"])
