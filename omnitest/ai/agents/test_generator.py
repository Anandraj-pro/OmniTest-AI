"""Generates BDD scenarios and Robot suites from a plain-language requirement."""
from __future__ import annotations

from omnitest.ai.client import Tier
from omnitest.ai.agents.base import BaseAgent


class TestGeneratorAgent(BaseAgent):
    tier = Tier.SMART  # test design needs the strongest model
    base_rules = [
        "Only produce test artifacts — no explanatory prose outside the requested format.",
        "Cover the happy path, at least one negative case, and one boundary case.",
        "Prefer stable, role/label-based selectors over brittle XPath.",
    ]

    def gherkin(self, requirement: str, *, feature: str = "Feature under test") -> str:
        return self.ask(
            task=f"Write a Gherkin .feature for this requirement:\n{requirement}",
            context=f"Feature area: {feature}. Consumed by pytest-bdd.",
            output="A valid Gherkin `.feature` file. Feature/Scenario/Given/When/Then only.",
            tags={"artifact": "gherkin"},
        )

    def robot_suite(self, requirement: str, *, resource: str = "resources/common.resource") -> str:
        return self.ask(
            task=f"Write a Robot Framework test suite for:\n{requirement}",
            context=(
                f"Robot Framework 7 is the PRIMARY test layer. Import `{resource}`. "
                "Keywords may call the AI library `OmniAI` and Playwright via Browser library."
            ),
            output="A complete `.robot` file with *** Settings ***, *** Test Cases ***, *** Keywords ***.",
            tags={"artifact": "robot"},
        )