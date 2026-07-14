"""Provider abstraction — lets any Tier route to Claude OR a local Ollama model.

A Provider takes a rendered TCRO (system + user text) and returns a Completion.
This is the seam that makes the framework multi-LLM: agents and TCRO never change,
only the (provider, model) a Tier maps to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class Completion:
    text: str
    model: str
    provider: str
    #: token counts — keys: input_tokens, output_tokens,
    #: cache_read_input_tokens, cache_creation_input_tokens
    usage: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class Provider(Protocol):
    #: short id used in logs/dashboard ("anthropic", "ollama")
    name: str

    def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        effort: str = "high",
        thinking: bool = True,
        prompt_cache: bool = True,
    ) -> Completion:
        """Run one prompt and return its text + token usage."""
        ...
