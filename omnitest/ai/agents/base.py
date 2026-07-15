"""BaseAgent — every agent declares its Tier and builds a TCRO prompt."""
from __future__ import annotations

import json
import re
from typing import Any

from omnitest.ai.client import AIClient, Tier
from omnitest.ai.context import get_story
from omnitest.ai.tcro import TCRO


class BaseAgent:
    #: default routing tier for this agent (subclasses override for cost control)
    tier: Tier = Tier.SMART
    #: shared Rules injected into every prompt this agent makes
    base_rules: list[str] = []

    def __init__(self, client: AIClient | None = None) -> None:
        self.client = client or AIClient.shared()

    @property
    def name(self) -> str:
        return type(self).__name__

    def ask(
        self,
        task: str,
        *,
        context: str = "",
        rules: list[str] | None = None,
        output: str = "",
        max_tokens: int = 4096,
        tags: dict[str, str] | None = None,
    ) -> str:
        tcro = TCRO(
            task=task,
            context=context,
            rules=[*self.base_rules, *(rules or [])],
            output=output,
        )
        # Attribute this call to the active user story (if any) for the director view.
        merged_tags = dict(tags or {})
        story_id = get_story()
        if story_id and "story" not in merged_tags:
            merged_tags["story"] = story_id
        return self.client.run(
            tcro, agent=self.name, tier=self.tier, max_tokens=max_tokens,
            tags=merged_tags or None,
        )

    # ── helpers ─────────────────────────────────────────
    @staticmethod
    def parse_json(text: str) -> Any:
        """Extract the first JSON object/array from a model response."""
        text = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        if fenced:
            text = fenced.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
            if m:
                return json.loads(m.group(1))
            raise