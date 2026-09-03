"""Auth tests.

What is worth testing here is not "does login return 200" — it is the security
properties, because those are the ones that fail silently. A login that works
and leaks which emails are registered passes any smoke test.
"""

from __future__ import annotations

import pytest

from app.security import hash_password, verify_password
from tests.conftest import GOOD_PASSWORD, register


class TestRegistration:
    async def test_registration_signs_you_in(self, client):
        response = await register(client)
        assert response.status_code == 201
        assert response.cookies.get("recall_session")

    async def test_a_short_password_is_rejected(self, client):
        response = await register(client, password="short")
        assert response.status_code == 422

    async def test_email_case_does_not_create_a_second_account(self, client):
        assert (await register(client, email="Sam@Example.com")).status_code == 201
        # Same person to everyone except a case-sensitive index.
        second = await register(client, email="sam@example.com")
        assert second.status_code == 409

    async def test_the_password_is_never_returned(self, client):
        body = (await register(client)).json()
        assert "password" not in body
        assert "password_hash" not in body


class TestLogin:
    async def test_correct_credentials_succeed(self, client):
        await register(client)
        response = await client.post(
            "/auth/login", json={"email": "a@b.com", "password": GOOD_PASSWORD}
        )
        assert response.status_code == 200
        assert response.cookies.get("recall_session")

    async def test_a_wrong_password_and_an_unknown_email_are_indistinguishable(self, client):
        """The account-enumeration test.

        If these two responses differ in any way, the login form tells an
        attacker which addresses are registered.
        """
        await register(client)
        wrong_password = await client.post(
            "/auth/login", json={"email": "a@b.com", "password": "not-the-password"}
        )
        unknown_email = await client.post(
            "/auth/login", json={"email": "nobody@b.com", "password": GOOD_PASSWORD}
        )

        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()


class TestSessionCookie:
    async def test_the_cookie_is_httponly_and_lax(self, client):
        """httponly is why an XSS bug cannot steal the session, and it is the
        reason the token is not in localStorage."""
        response = await register(client)
        header = response.headers["set-cookie"].lower()
        assert "httponly" in header
        assert "samesite=lax" in header

    async def test_me_returns_the_signed_in_user(self, client):
        await register(client, email="sam@example.com")
        response = await client.get("/auth/me")
        assert response.status_code == 200
        assert response.json()["email"] == "sam@example.com"

    async def test_me_without_a_cookie_is_401(self, client):
        assert (await client.get("/auth/me")).status_code == 401

    async def test_a_tampered_cookie_is_rejected(self, client):
        """The signature's whole job. Without it the cookie is just a claim."""
        await register(client)
        client.cookies.set("recall_session", "some-other-session-id")
        assert (await client.get("/auth/me")).status_code == 401

    async def test_logout_ends_the_session_server_side(self, client):
        """Clearing the cookie is not enough — a copy of it must stop working."""
        await register(client)
        stolen = client.cookies.get("recall_session")

        assert (await client.post("/auth/logout")).status_code == 200

        client.cookies.set("recall_session", stolen)
        assert (await client.get("/auth/me")).status_code == 401


class TestHashing:
    def test_a_hash_does_not_contain_the_password(self):
        digest = hash_password(GOOD_PASSWORD)
        assert GOOD_PASSWORD not in digest
        assert digest.startswith("$argon2id$")

    def test_the_same_password_hashes_differently_each_time(self):
        """Per-hash salt. Identical hashes would reveal shared passwords."""
        assert hash_password(GOOD_PASSWORD) != hash_password(GOOD_PASSWORD)

    def test_verification_returns_false_rather_than_raising(self):
        digest = hash_password(GOOD_PASSWORD)
        assert verify_password(digest, GOOD_PASSWORD) is True
        assert verify_password(digest, "wrong") is False
        # A corrupted row must fail to authenticate, not 500 the endpoint.
        assert verify_password("not-a-hash", GOOD_PASSWORD) is False

    def test_a_long_passphrase_is_not_truncated(self):
        """bcrypt silently truncates at 72 bytes, turning a long passphrase
        into a shorter one. argon2 does not, and this proves it: two passwords
        identical for the first 72 bytes must not verify against each other."""
        base = "a" * 72
        digest = hash_password(base + "-first")
        assert verify_password(digest, base + "-second") is False
