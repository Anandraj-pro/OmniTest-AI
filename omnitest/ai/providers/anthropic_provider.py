"""Claude provider — prompt caching, adaptive thinking, streaming for big outputs."""
from __future__ import annotations

from typing import Any

import anthropic

from omnitest.ai.providers.base import Completion

_DEFAULT_SYSTEM = "You are a precise test-automation assistant."


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str = "") -> None:
        # Empty key -> zero-arg client resolves the subscription OAuth profile
        # (`claude` / `ant auth login`). A set key -> pay-per-token API billing.
        self._client = (
            anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        )

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
        sys_field: Any = system or _DEFAULT_SYSTEM
        if prompt_cache and system:
            # Cache the stable Context+Rules half so repeated calls are cheap.
            sys_field = [{"type": "text", "text": system,
                          "cache_control": {"type": "ephemeral"}}]

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": sys_field,
            "messages": [{"role": "user", "content": user}],
        }
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": effort}

        # Stream when max_tokens is large to avoid HTTP timeouts.
        if max_tokens > 16000:
            with self._client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
        else:
            msg = self._client.messages.create(**kwargs)

        text = "".join(b.text for b in msg.content if b.type == "text")
        return Completion(text=text, model=model, provider=self.name,
                          usage=_usage_dict(msg.usage))


def _usage_dict(usage: Any) -> dict[str, int]:
    keys = ("input_tokens", "output_tokens",
            "cache_creation_input_tokens", "cache_read_input_tokens")
    return {k: int(getattr(usage, k, 0) or 0) for k in keys}
