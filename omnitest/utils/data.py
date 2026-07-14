"""Test-data helpers (Faker-backed)."""
from __future__ import annotations

from faker import Faker

_fake = Faker()


class DataFactory:
    @staticmethod
    def email(domain: str = "omnitest.dev") -> str:
        return f"{_fake.user_name()}.{_fake.random_int(1000, 9999)}@{domain}"

    @staticmethod
    def name() -> str:
        return _fake.name()

    @staticmethod
    def password(length: int = 14) -> str:
        return _fake.password(length=length, special_chars=True, digits=True)

    @staticmethod
    def user() -> dict[str, str]:
        return {
            "name": DataFactory.name(),
            "email": DataFactory.email(),
            "password": DataFactory.password(),
        }