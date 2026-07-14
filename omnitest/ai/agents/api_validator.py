"""Semantic validation of API responses (beyond strict schema checks)."""
from __future__ import annotations

from typing import Any

from omnitest.ai.client import Tier
from omnitest.ai.agents.base import BaseAgent


class ApiValidatorAgent(BaseAgent):
    tier = Tier.BALANCED
    base_rules = [
        "Base the verdict only on the response and the stated expectation.",
        "Return strict JSON. No commentary.",
    ]

    def assess(self, *, response_json: str, expectation: str, status: int) -> dict[str, Any]:
        raw = self.ask(
            task="Determine whether the API response meets the expectation.",
            context=f"HTTP status: {status}\n\nRESPONSE:\n{response_json}\n\nEXPECTATION:\n{expectation}",
            output='JSON: {"pass": bool, "reason": str, "violations": [str]}',
            tags={"artifact": "api_check"},
        )
        return self.parse_json(raw)

    def suggest_assertions(self, *, response_json: str) -> list[str]:
        raw = self.ask(
            task="Propose meaningful assertions for this API response.",
            context=f"RESPONSE:\n{response_json}",
            output='JSON array of assertion strings (human-readable).',
            tags={"artifact": "api_assertions"},
        )
        return self.parse_json(raw)