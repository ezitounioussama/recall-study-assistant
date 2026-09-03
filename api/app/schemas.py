"""Request and response shapes for auth."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalise(cls, value: str) -> str:
        # Lowercased here rather than at the query, so registration and login
        # cannot disagree about whether two spellings are one account.
        return value.strip().lower()


class Registration(Credentials):
    display_name: str = Field(min_length=1, max_length=80)

    # 12 characters, no composition rules. Length is what resists an offline
    # attack; a mandatory symbol mostly produces "Password1!" and a reminder
    # note. NIST 800-63B says the same.
    password: str = Field(min_length=12, max_length=200)


class PublicUser(BaseModel):
    id: str
    email: EmailStr
    display_name: str


class Message(BaseModel):
    detail: str
