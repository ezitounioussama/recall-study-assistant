"""Bearer tokens: what they prove, and every way one can fail to.

The cookie has its own file. These are the properties of the second door:
a token that is expired, tampered with, signed by someone else, or issued for
an account that no longer exists must all fail the same way.
"""

from __future__ import annotations

import datetime as dt

import jwt
import pytest

from app.config import settings
from app.security import create_access_token, decode_access_token
from tests.conftest import GOOD_PASSWORD, register


async def get_token(client, email: str = "a@b.com", password: str = GOOD_PASSWORD) -> str:
    response = await client.post("/auth/token", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestIssuing:
    async def test_email_and_password_buy_a_bearer_token(self, client):
        await register(client)
        response = await client.post("/auth/token", data={"username": "a@b.com", "password": GOOD_PASSWORD})

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == settings().access_token_expire_minutes * 60
        assert body["access_token"].count(".") == 2  # header.payload.signature

    async def test_the_email_is_case_insensitive_like_login(self, client):
        await register(client, email="sam@example.com")
        response = await client.post("/auth/token", data={"username": "SAM@Example.com", "password": GOOD_PASSWORD})
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "username, password",
        [("a@b.com", "wrong-password-entirely"), ("nobody@nowhere.com", GOOD_PASSWORD)],
    )
    async def test_a_wrong_password_and_an_unknown_email_fail_identically(self, client, username, password):
        await register(client)
        response = await client.post("/auth/token", data={"username": username, "password": password})

        assert response.status_code == 401
        assert response.json()["detail"] == "Email or password is incorrect."

    async def test_the_token_carries_no_secret_and_no_personal_data(self, client):
        await register(client, email="sam@example.com")
        token = await get_token(client, "sam@example.com")

        payload = jwt.decode(token, settings().session_secret, algorithms=["HS256"])
        assert set(payload) == {"sub", "iat", "exp", "jti", "typ"}
        assert "sam@example.com" not in token
        assert GOOD_PASSWORD not in token


class TestUsingOne:
    async def test_a_token_authenticates_a_protected_route(self, client):
        await register(client)
        token = await get_token(client)
        client.cookies.clear()  # prove it is the token doing the work

        response = await client.get("/auth/me", headers=bearer(token))
        assert response.status_code == 200
        assert response.json()["email"] == "a@b.com"

    async def test_it_works_on_every_protected_route_not_just_me(self, client):
        await register(client)
        token = await get_token(client)
        client.cookies.clear()

        assert (await client.get("/documents", headers=bearer(token))).status_code == 200
        assert (await client.get("/cards/due", headers=bearer(token))).status_code == 200
        assert (await client.get("/study/history", headers=bearer(token))).status_code == 200

    async def test_no_credential_at_all_is_401(self, client):
        client.cookies.clear()
        response = await client.get("/auth/me")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


class TestRejecting:
    @pytest.fixture
    async def user_id(self, client) -> str:
        await register(client)
        return (await client.get("/auth/me")).json()["id"]

    async def test_garbage_is_not_a_token(self, client):
        client.cookies.clear()
        assert (await client.get("/auth/me", headers=bearer("not-a-token"))).status_code == 401

    async def test_a_tampered_payload_fails_the_signature(self, client, user_id):
        token = await get_token(client)
        client.cookies.clear()
        header, payload, signature = token.split(".")
        forged = f"{header}.{payload[:-4]}AAAA.{signature}"
        assert (await client.get("/auth/me", headers=bearer(forged))).status_code == 401

    async def test_a_token_signed_with_another_secret_is_refused(self, client, user_id):
        client.cookies.clear()
        forged = jwt.encode({"sub": user_id, "typ": "access"}, "a-different-secret-entirely-and-long-enough-for-hmac", algorithm="HS256")
        assert (await client.get("/auth/me", headers=bearer(forged))).status_code == 401

    async def test_an_unsigned_token_is_refused(self, client, user_id):
        """`alg: none` is the classic JWT hole. The decoder pins its algorithm."""
        client.cookies.clear()
        unsigned = jwt.encode({"sub": user_id, "typ": "access"}, key="", algorithm="none")
        assert (await client.get("/auth/me", headers=bearer(unsigned))).status_code == 401

    async def test_an_expired_token_is_refused(self, client, user_id):
        client.cookies.clear()
        expired = create_access_token(user_id, expires_minutes=-1)
        assert (await client.get("/auth/me", headers=bearer(expired))).status_code == 401

    async def test_a_token_for_an_account_that_no_longer_exists_is_refused(self, client):
        client.cookies.clear()
        orphan = create_access_token("00000000-0000-0000-0000-000000000000")
        assert (await client.get("/auth/me", headers=bearer(orphan))).status_code == 401

    async def test_a_token_of_the_wrong_type_is_refused(self, client, user_id):
        """Only tokens minted as access tokens open a door."""
        client.cookies.clear()
        other = jwt.encode(
            {"sub": user_id, "typ": "refresh", "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)},
            settings().session_secret,
            algorithm="HS256",
        )
        assert (await client.get("/auth/me", headers=bearer(other))).status_code == 401


class TestDecoder:
    def test_a_round_trip_returns_the_subject(self):
        assert decode_access_token(create_access_token("user-42")) == "user-42"

    def test_every_failure_returns_none_rather_than_raising(self):
        assert decode_access_token("rubbish") is None
        assert decode_access_token(create_access_token("user-42", expires_minutes=-1)) is None


class TestTwoDoorsOneHouse:
    async def test_the_cookie_still_works_and_the_two_agree(self, client):
        await register(client, email="sam@example.com")
        by_cookie = (await client.get("/auth/me")).json()

        token = await get_token(client, "sam@example.com")
        client.cookies.clear()
        by_token = (await client.get("/auth/me", headers=bearer(token))).json()

        assert by_cookie == by_token

    async def test_a_bearer_token_wins_over_a_stale_cookie(self, client):
        """An explicit header is a deliberate act; a cookie rides along."""
        await register(client, email="alice@x.com")
        alice_cookie_still_set = client.cookies.get("recall_session")
        assert alice_cookie_still_set

        await register(client, email="bob@x.com")  # bob's cookie replaces alice's
        bob_token = await get_token(client, "bob@x.com")
        client.cookies.set("recall_session", alice_cookie_still_set)

        assert (await client.get("/auth/me", headers=bearer(bob_token))).json()["email"] == "bob@x.com"
