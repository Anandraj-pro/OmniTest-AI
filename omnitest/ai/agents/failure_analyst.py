"""Root-cause analysis of test failures and self-healing selector suggestions."""
from __future__ import annotations

from typing import Any

from omnitest.ai.client import Tier
from omnitest.ai.agents.base import BaseAgent


class FailureAnalystAgent(BaseAgent):
    tier = Tier.SMART
    base_rules = ["Be specific and actionable. Return strict JSON."]

    def diagnose(self, *, test: str, error: str, logs: str = "") -> dict[str, Any]:
        raw = self.ask(
            task="Diagnose the likely root cause of this test failure and suggest a fix.",
            context=f"TEST: {test}\n\nERROR:\n{error}\n\nLOGS:\n{logs[:6000]}",
            output=(
                'JSON: {"root_cause": str, "category": '
                '"product-bug|test-bug|flaky|env|data", "suggested_fix": str, '
                '"confidence": number}'
            ),
            tags={"artifact": "failure_diagnosis"},
        )
        return self.parse_json(raw)

    def heal_selector(self, *, broken: str, dom_snippet: str, intent: str) -> dict[str, Any]:
        """Suggest a resilient replacement selector when the original no longer matches."""
        raw = self.ask(
            task="The selector no longer matches. Propose a robust replacement.",
            context=f"BROKEN SELECTOR: {broken}\nINTENT: {intent}\n\nDOM:\n{dom_snippet[:6000]}",
            output='JSON: {"selector": str, "strategy": "role|label|text|css|xpath", "reason": str}',
            tags={"artifact": "self_heal"},
        )
        return self.parse_json(raw)