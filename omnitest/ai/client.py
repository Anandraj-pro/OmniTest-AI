"""AI client with multi-provider model routing, prompt caching, and TCRO tracking.

Model routing keeps spend down: each agent picks the *cheapest tier that can do
the job*, and each tier maps to a (provider, model) pair — so a tier can run on
Claude OR on a local Ollama model (free). Nothing above this file changes.

    Tier.CHEAP     -> e.g. ollama/qwen2.5:7b  classification, extraction, yes/no
    Tier.BALANCED  -> e.g. sonnet-5           content/context validation
    Tier.SMART     -> e.g. opus-4-8           test generation, root-cause, self-heal

Configure per-tier provider+model in .env (OMNI_PROVIDER_* / OMNI_MODEL_*).
Everything routes through `run()`, which logs the full TCRO input + output.
"""
from __future__ import annotations

import enum

from omnitest.config import settings
from omnitest.ai.tcro import TCRO
from omnitest.ai.tracker import PromptTracker
from omnitest.ai.providers import Provider, make_provider


class Tier(enum.Enum):
    CHEAP = "cheap"
    BALANCED = "balanced"
    SMART = "smart"


class AIClient:
    _shared: "AIClient | None" = None

    def __init__(self) -> None:
        self._tracker = PromptTracker(settings.abs_prompt_log_dir)
        # Each tier -> (provider name, model). Providers are resolved lazily and
        # shared via make_provider's cache.
        self._routes: dict[Tier, tuple[str, str]] = {
            Tier.CHEAP: (settings.provider_cheap, settings.model_cheap),
            Tier.BALANCED: (settings.provider_balanced, settings.model_balanced),
            Tier.SMART: (settings.provider_smart, settings.model_smart),
        }

    @classmethod
    def shared(cls) -> "AIClient":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @property
    def tracker(self) -> PromptTracker:
        return self._tracker

    def provider_for(self, tier: Tier) -> Provider:
        return make_provider(self._routes[tier][0])

    def model_for(self, tier: Tier) -> str:
        return self._routes[tier][1]

    def run(
        self,
        tcro: TCRO,
        *,
        agent: str,
        tier: Tier = Tier.SMART,
        max_tokens: int = 4096,
        effort: str = "high",
        thinking: bool = True,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Execute a TCRO prompt and return the response text (also logged)."""
        provider_name, model = self._routes[tier]
        provider = make_provider(provider_name)
        started = self._tracker.start()

        try:
            result = provider.complete(
                system=tcro.system_text(),
                user=tcro.user_text(),
                model=model,
                max_tokens=max_tokens,
                effort=effort,
                thinking=thinking,
                prompt_cache=settings.prompt_cache,
            )
        except Exception as exc:  # noqa: BLE001 — log then re-raise
            self._tracker.record(
                agent=agent, model=model, tier=tier.value, provider=provider_name,
                tcro=tcro.to_dict(), response="", usage={}, started=started,
                ok=False, error=f"{type(exc).__name__}: {exc}", tags=tags,
            )
            raise

        self._tracker.record(
            agent=agent, model=model, tier=tier.value, provider=provider_name,
            tcro=tcro.to_dict(), response=result.text, usage=result.usage,
            started=started, tags=tags,
        )
        return result.text
