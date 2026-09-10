"""A small HTTP client for the Recall API, with the credential handling.

Separate from the tools so the tools stay readable and so the tests can hand
the server a client pointed at a fake API.

Credentials come from the environment. They are never tool arguments: an
argument is chosen by the model, and a model should not be in a position to
send a password anywhere, nor to receive one back in a result.
"""

from __future__ import annotations

import os

import httpx

DEFAULT_URL = "http://localhost:8100"


class RecallError(RuntimeError):
    """Something the caller should be told in a sentence."""


class RecallClient:
    """Talks to one Recall account.

    Signs in once with the email and password from the environment, keeps the
    bearer token, and re-authenticates if the API ever says it has expired.
    """

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 600.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("RECALL_API_URL", DEFAULT_URL)).rstrip("/")
        self._email = email if email is not None else os.environ.get("RECALL_EMAIL", "")
        self._password = password if password is not None else os.environ.get("RECALL_PASSWORD", "")
        self._token: str | None = os.environ.get("RECALL_TOKEN") or None
        self._transport = transport
        # Generous: a checklist from a local model on a CPU takes tens of
        # seconds, and the API applies its own bound before this one matters.
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout, transport=self._transport)

    async def _authenticate(self) -> str:
        if not self._email or not self._password:
            raise RecallError(
                "No Recall credentials. Set RECALL_EMAIL and RECALL_PASSWORD in the MCP server's "
                "environment, or RECALL_TOKEN if you already have one."
            )
        async with self._client() as http:
            try:
                response = await http.post(
                    "/auth/token", data={"username": self._email, "password": self._password}
                )
            except httpx.HTTPError as exc:
                raise RecallError(f"Cannot reach the Recall API at {self.base_url}. Is it running?") from exc

        if response.status_code == 401:
            raise RecallError("Recall rejected those credentials. Check RECALL_EMAIL and RECALL_PASSWORD.")
        response.raise_for_status()
        self._token = response.json()["access_token"]
        return self._token

    async def request(self, method: str, path: str, **kwargs) -> dict | list:
        """One authenticated call, retried once if the token has expired."""
        token = self._token or await self._authenticate()

        for attempt in (1, 2):
            async with self._client() as http:
                try:
                    response = await http.request(
                        method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
                    )
                except httpx.TimeoutException as exc:
                    raise RecallError(
                        "Recall took too long to answer. The model may be busy; try a narrower topic."
                    ) from exc
                except httpx.HTTPError as exc:
                    raise RecallError(f"Cannot reach the Recall API at {self.base_url}. Is it running?") from exc

            if response.status_code == 401 and attempt == 1:
                # The token expired between calls. Get another and try again;
                # a second 401 is a real credentials problem.
                token = await self._authenticate()
                continue
            break

        if response.status_code >= 400:
            raise RecallError(_message(response))
        return response.json()

    async def get(self, path: str, **kwargs) -> dict | list:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, payload: dict) -> dict | list:
        return await self.request("POST", path, json=payload)


def _message(response: httpx.Response) -> str:
    """The API's own sentence when it has one, never a raw body dump."""
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        return "Recall rejected that request: check the arguments."
    return f"Recall returned {response.status_code}."
