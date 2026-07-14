"""Pydantic models for test data and API contracts.

Use these to build valid payloads and to validate responses with real type
checking (complementing the AI semantic checks in ApiValidatorAgent).
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from omnitest.utils.data import DataFactory


class User(BaseModel):
    name: str
    email: str
    password: str | None = None

    @classmethod
    def fake(cls) -> "User":
        d = DataFactory.user()
        return cls(**d)


class CreatedUser(BaseModel):
    """Expected shape of POST /users response — used with expect_schema/model_validate."""
    id: int | str
    name: str
    email: str
    created_at: str | None = None


class HealthStatus(BaseModel):
    status: str = Field(..., description="e.g. 'ok' / 'healthy' / 'up'")
    version: str | None = None