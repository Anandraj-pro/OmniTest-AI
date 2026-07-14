"""Provider registry + factory. Add a new LLM backend here in one place."""
from __future__ import annotations

from functools import lru_cache

from omnitest.config import settings
from omnitest.ai.providers.base import Completion, Provider
from omnitest.ai.providers.anthropic_provider import AnthropicProvider
from omnitest.ai.providers.ollama_provider import OllamaProvider

__all__ = ["Completion", "Provider", "make_provider"]


@lru_cache
def make_provider(name: str) -> Provider:
    """Return a shared provider instance by name ('anthropic' | 'ollama')."""
    key = name.lower().strip()
    if key == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if key == "ollama":
        return OllamaProvider(host=settings.ollama_host)
    raise ValueError(f"Unknown provider {name!r}. Expected 'anthropic' or 'ollama'.")
