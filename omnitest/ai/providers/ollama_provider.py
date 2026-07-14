"""Ollama provider — local, free inference (e.g. qwen2.5:7b).

Uses Ollama's native /api/chat endpoint over httpx (already a dependency).
Thinking / effort / prompt-cache flags don't apply locally and are ignored.
No cost: these calls are logged with cost_usd = 0.

Prereqs:
    ollama serve            # running on OMNI_OLLAMA_HOST (default :11434)
    ollama pull qwen2.5:7b  # or whatever OMNI_OLLAMA_MODEL points to
"""
from __future__ import annotations

import httpx

from omnitest.ai.providers.base import Completion


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        self._host = host.rstrip("/")
        self._timeout = timeout

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
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        resp = httpx.post(f"{self._host}/api/chat", json=payload, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()

        text = data.get("message", {}).get("content", "")
        # Ollama returns token counts; map to the same keys Claude uses so the
        # tracker/dashboard stay uniform. Cache fields are always 0 locally.
        usage = {
            "input_tokens": int(data.get("prompt_eval_count", 0) or 0),
            "output_tokens": int(data.get("eval_count", 0) or 0),
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        return Completion(text=text, model=model, provider=self.name, usage=usage)
