"""Validates received-email *content* and *context* semantically.

Cheap tier: this is classification/verification, not generation — Haiku is plenty
and keeps token cost minimal.
"""
from __future__ import annotations

from typing import Any

from omnitest.ai.client import Tier
from omnitest.ai.agents.base import BaseAgent


class EmailAnalyzerAgent(BaseAgent):
    tier = Tier.CHEAP
    base_rules = [
        "Judge only what the expectation states — do not invent extra requirements.",
        "Return strict JSON. No commentary.",
    ]

    def verify(self, *, subject: str, body: str, expectation: str) -> dict[str, Any]:
        """Return {"pass": bool, "reason": str, "matched": [...], "missing": [...]}."""
        raw = self.ask(
            task=(
                "Decide whether the email satisfies the expectation, considering both "
                "explicit content and contextual intent."
            ),
            context=f"SUBJECT: {subject}\n\nBODY:\n{body}\n\nEXPECTATION:\n{expectation}",
            output='JSON: {"pass": bool, "reason": str, "matched": [str], "missing": [str]}',
            tags={"artifact": "email_check"},
        )
        return self.parse_json(raw)

    def extract(self, *, body: str, fields: list[str]) -> dict[str, Any]:
        """Pull structured fields (e.g. OTP, order id, reset link) out of an email body."""
        raw = self.ask(
            task=f"Extract these fields from the email body: {', '.join(fields)}.",
            context=f"BODY:\n{body}",
            output='JSON object keyed by field name; use null when a field is absent.',
            tags={"artifact": "email_extract"},
        )
        return self.parse_json(raw)