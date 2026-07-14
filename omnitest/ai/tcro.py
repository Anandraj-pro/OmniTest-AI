"""TCRO prompt structure — the mandatory input shape for every AI call.

    T  Task      What the agent must do (the specific, per-request ask).
    C  Context   Stable domain/system information the agent needs.
    R  Rules     Constraints / guardrails the output must obey.
    O  Output    The exact response format required.

Your manager can audit every prompt because each call is built from — and logged
as — a TCRO object (see PromptTracker).

Caching note: Context + Rules are stable across a run and are rendered into the
`system` prompt with a cache breakpoint, so repeated calls only pay full price
for the varying Task + Output. This is what keeps token spend low.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TCRO:
    task: str
    context: str = ""
    rules: list[str] = field(default_factory=list)
    output: str = ""

    def __post_init__(self) -> None:
        if not self.task or not self.task.strip():
            raise ValueError("TCRO.task is required and must be non-empty")

    # ── rendering ───────────────────────────────────────
    def system_text(self) -> str:
        """Stable half (Context + Rules) — goes in the cached system prompt."""
        parts: list[str] = []
        if self.context:
            parts.append(f"# CONTEXT\n{self.context}")
        if self.rules:
            joined = "\n".join(f"- {r}" for r in self.rules)
            parts.append(f"# RULES\n{joined}")
        return "\n\n".join(parts).strip()

    def user_text(self) -> str:
        """Varying half (Task + Output) — goes in the user message."""
        parts = [f"# TASK\n{self.task}"]
        if self.output:
            parts.append(f"# OUTPUT FORMAT\n{self.output}")
        return "\n\n".join(parts).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "context": self.context,
            "rules": list(self.rules),
            "output": self.output,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)