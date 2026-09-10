"""The capstone acceptance suite: one student's whole journey, in order.

The other test files take one part of the system and press on it hard. This
one reads top to bottom as the thing a person actually does — arrive, register,
sign in, be refused without a credential, be refused with bad input, study
something, find it in their history — and asserts the property that matters at
each step.

It exists so a reviewer can read one file and see the requirements met, and so
a regression in the seam between two parts fails here even when both parts'
own tests still pass.
"""

from __future__ import annotations

import json

import pytest

from app.llm import get_chat_model
from app.main import app
from tests.test_documents import BIOLOGY, upload

EMAIL = "student@university.edu"
PASSWORD = "long-enough-to-be-a-passphrase"

EXPLANATION = "Mitochondria produce ATP through oxidative phosphorylation [1]."
QUIZ = json.dumps(
    {
        "questions": [
            {
                "question": "What do mitochondria produce?",
                "choices": ["ATP", "Chlorophyll", "Glucose", "DNA"],
                "answer": "ATP",
                "explanation": "Mitochondria produce ATP [1].",
                "source_index": 1,
            }
        ]
    }
)


class Model:
    """A model that answers with whatever this test needs."""

    model = "test-model"
    timeout = 30.0

    def __init__(self, reply: str = EXPLANATION) -> None:
        self.reply = reply

    async def complete(self, system, messages, *, json_mode: bool = False) -> str:
        return self.reply

    async def stream(self, system, messages):
        yield self.reply


@pytest.fixture
def model():
    scripted = Model()
    app.dependency_overrides[get_chat_model] = lambda: scripted
    yield scripted
    app.dependency_overrides.pop(get_chat_model, None)


# ---- 1. the service is up ---------------------------------------------------------


class TestHealth:
    async def test_health_answers_without_a_credential(self, client):
        client.cookies.clear()
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_the_root_says_what_this_is(self, client):
        client.cookies.clear()
        body = (await client.get("/")).json()
        assert body["name"] == "Recall API"
        assert body["docs"] == "/docs"


# ---- 2. registration ---------------------------------------------------------------


class TestRegistration:
    async def test_a_new_student_can_register_and_is_signed_in(self, client):
        response = await client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "A Student"},
        )

        assert response.status_code == 201
        assert response.json()["email"] == EMAIL
        assert response.cookies.get("recall_session")

    async def test_the_password_is_never_returned_and_never_stored_in_the_clear(self, client):
        from sqlalchemy import select

        from app.db import SessionFactory
        from app.models import User

        response = await client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "A Student"},
        )
        assert PASSWORD not in response.text

        async with SessionFactory() as db:
            user = await db.scalar(select(User).where(User.email == EMAIL))
        assert user is not None
        assert PASSWORD not in user.password_hash
        assert user.password_hash.startswith("$argon2id$")

    async def test_the_same_address_cannot_register_twice(self, client):
        payload = {"email": EMAIL, "password": PASSWORD, "display_name": "A Student"}
        assert (await client.post("/auth/register", json=payload)).status_code == 201
        assert (await client.post("/auth/register", json=payload)).status_code == 409


# ---- 3. login ------------------------------------------------------------------------


class TestLogin:
    @pytest.fixture(autouse=True)
    async def _registered(self, client):
        await client.post(
            "/auth/register", json={"email": EMAIL, "password": PASSWORD, "display_name": "A Student"}
        )
        client.cookies.clear()

    async def test_the_right_password_signs_you_in(self, client):
        response = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

        assert response.status_code == 200
        assert response.cookies.get("recall_session")
        assert (await client.get("/auth/me")).json()["email"] == EMAIL

    async def test_the_wrong_password_does_not(self, client):
        response = await client.post("/auth/login", json={"email": EMAIL, "password": "not-the-password"})
        assert response.status_code == 401

    async def test_a_script_can_get_a_bearer_token_instead(self, client):
        token = (await client.post("/auth/token", data={"username": EMAIL, "password": PASSWORD})).json()
        client.cookies.clear()

        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"})
        assert response.status_code == 200

    async def test_signing_out_ends_the_session_immediately(self, client):
        await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        cookie = client.cookies.get("recall_session")

        await client.post("/auth/logout")
        client.cookies.set("recall_session", cookie)  # a copy someone kept

        assert (await client.get("/auth/me")).status_code == 401


# ---- 4. protected routes ---------------------------------------------------------------

PROTECTED = [
    ("GET", "/auth/me"),
    ("GET", "/documents"),
    ("GET", "/cards/due"),
    ("GET", "/cards/stats"),
    ("GET", "/study/history"),
    ("POST", "/study/explain"),
    ("POST", "/study/quiz"),
    ("POST", "/chat"),
]


class TestProtection:
    @pytest.mark.parametrize("method, path", PROTECTED)
    async def test_no_credential_no_entry(self, client, method, path):
        client.cookies.clear()
        response = await client.request(method, path, json={"topic": "mitochondria", "question": "what?"})
        assert response.status_code == 401

    @pytest.mark.parametrize("method, path", PROTECTED)
    async def test_a_forged_cookie_is_not_a_credential(self, client, method, path):
        client.cookies.clear()
        client.cookies.set("recall_session", "a-value-i-made-up")
        response = await client.request(method, path, json={"topic": "mitochondria", "question": "what?"})
        assert response.status_code == 401


# ---- 5. invalid input --------------------------------------------------------------------


class TestInvalidInput:
    @pytest.mark.parametrize(
        "path, payload, why",
        [
            ("/auth/register", {"email": "not-an-address", "password": PASSWORD, "display_name": "X"}, "email"),
            ("/auth/register", {"email": EMAIL, "password": "short", "display_name": "X"}, "password"),
            ("/auth/register", {"email": EMAIL, "password": PASSWORD}, "display_name"),
            ("/study/explain", {"topic": ""}, "empty topic"),
            ("/study/explain", {"topic": "x" * 501}, "enormous topic"),
            ("/study/quiz", {"topic": "mitochondria", "count": 99}, "count out of range"),
            ("/chat", {"question": ""}, "empty question"),
        ],
    )
    async def test_a_bad_request_is_422_before_any_work(self, signed_in, path, payload, why):
        assert (await signed_in.post(path, json=payload)).status_code == 422, why

    async def test_an_unsupported_file_is_refused_with_a_useful_message(self, signed_in):
        response = await signed_in.post("/documents", files={"file": ("slides.pptx", b"PK\x03\x04")})
        assert response.status_code == 415
        assert ".pdf" in response.json()["detail"]

    async def test_an_id_that_does_not_exist_is_404_not_500(self, signed_in):
        assert (await signed_in.get("/documents/no-such-id")).status_code == 404
        assert (await signed_in.get("/cards/no-such-id")).status_code == 404
        assert (await signed_in.get("/study/history/no-such-id")).status_code == 404


# ---- 6. the study features, end to end ------------------------------------------------------


class TestStudyingSomething:
    async def test_the_whole_journey(self, client, model):
        """Register, upload, explain, quiz, review a card, read the history."""
        await client.post(
            "/auth/register", json={"email": EMAIL, "password": PASSWORD, "display_name": "A Student"}
        )

        # Upload material. It is split into passages and embedded.
        document = (await upload(client, name="cell-biology.md", content=BIOLOGY)).json()
        assert document["chunk_count"] >= 1

        # Explain a topic from it. The answer cites the passage it came from.
        explained = (await client.post("/study/explain", json={"topic": "mitochondria and ATP"})).json()
        assert explained["explanation"]["grounded"] is True
        assert explained["explanation"]["citations"] == [1]
        assert explained["sources"][0]["document_id"] == document["id"]

        # Generate a quiz. The answer key points at a real choice.
        model.reply = QUIZ
        quiz = (await client.post("/study/quiz", json={"topic": "mitochondria", "count": 1})).json()
        question = quiz["quiz"]["questions"][0]
        assert question["choices"][question["answer_index"]] == "ATP"

        # Turn the material into cards, and review one.
        model.reply = json.dumps({"cards": [{"front": "What makes ATP?", "back": "Mitochondria."}]})
        cards = (await client.post("/study/flashcards", json={"topic": "mitochondria", "count": 1})).json()
        card_id = cards["cards"][0]["id"]

        due_before = (await client.get("/cards/due")).json()
        assert card_id in [c["id"] for c in due_before]

        result = (await client.post(f"/cards/{card_id}/review", json={"rating": 3})).json()
        assert result["card"]["reps"] == 1
        assert result["log"]["scheduled_seconds"] > 0
        assert card_id not in [c["id"] for c in (await client.get("/cards/due")).json()]

        # Everything is in the history, newest first, with its structure.
        history = (await client.get("/study/history")).json()
        assert [s["kind"] for s in history] == ["flashcards", "quiz", "explain"]

        detail = (await client.get(f"/study/history/{history[-1]['id']}")).json()
        assert detail["contents"][0]["text"] == EXPLANATION
        assert detail["contents"][0]["data"]["citations"] == [1]

    async def test_what_the_notes_do_not_cover_is_refused_not_invented(self, signed_in, model):
        await upload(signed_in, content=BIOLOGY)
        result = (await signed_in.post("/study/explain", json={"topic": "zebra tango xylophone"})).json()

        assert result["explanation"]["grounded"] is False
        assert result["explanation"]["text"] == "I can't find that in your notes."
        assert result["sources"] == []


# ---- 7. one student cannot see another's ------------------------------------------------------


class TestIsolation:
    async def test_a_second_student_sees_an_empty_account(self, client, model):
        await client.post(
            "/auth/register", json={"email": EMAIL, "password": PASSWORD, "display_name": "First"}
        )
        await upload(client, content=BIOLOGY)
        await client.post("/study/explain", json={"topic": "mitochondria"})
        first_session = (await client.get("/study/history")).json()[0]["id"]
        first_document = (await client.get("/documents")).json()[0]["id"]

        client.cookies.clear()
        await client.post(
            "/auth/register", json={"email": "other@university.edu", "password": PASSWORD, "display_name": "Second"}
        )

        assert (await client.get("/documents")).json() == []
        assert (await client.get("/study/history")).json() == []
        assert (await client.get("/cards")).json() == []
        assert (await client.get(f"/documents/{first_document}")).status_code == 404
        assert (await client.get(f"/study/history/{first_session}")).status_code == 404

        # And their own question finds nothing, because retrieval is scoped too.
        result = (await client.post("/study/explain", json={"topic": "mitochondria"})).json()
        assert result["sources"] == []
