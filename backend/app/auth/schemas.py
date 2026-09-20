from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError(
                "Username may contain letters, numbers, dots, dashes, and underscores."
            )
        return normalized

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name must not be empty.")
        return normalized


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserView(BaseModel):
    id: UUID
    username: str
    display_name: str
    created_at: datetime


class WorkspaceView(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str


class AuthSessionView(BaseModel):
    user: UserView
    workspace: WorkspaceView
