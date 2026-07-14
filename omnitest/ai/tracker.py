"""Prompt input/output tracking for manager visibility.

Every AI call is appended to a JSONL file: TCRO input, model, response text,
token usage, cost, latency, and cache-hit tokens. `omnitest.reporting.prompt_dashboard`
turns the JSONL into an HTML report.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# USD per 1M tokens (input, output). Cache reads bill ~0.1x input; writes ~1.25x.
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _cost(model: str, usage: dict[str, int], provider: str = "anthropic") -> float:
    # Local providers (e.g. Ollama) are free — no token billing.
    if provider != "anthropic":
        return 0.0
    in_rate, out_rate = _PRICING.get(model, (5.0, 25.0))
    fresh = usage.get("input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_write = usage.get("cache_creation_input_tokens", 0)
    out = usage.get("output_tokens", 0)
    return round(
        (fresh * in_rate + cache_read * in_rate * 0.1 + cache_write * in_rate * 1.25 + out * out_rate)
        / 1_000_000,
        6,
    )


@dataclass(slots=True)
class PromptRecord:
    id: str
    timestamp: str
    agent: str
    model: str
    tier: str
    provider: str
    tcro: dict[str, Any]
    response: str
    usage: dict[str, int]
    cost_usd: float
    latency_ms: int
    ok: bool = True
    error: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


class PromptTracker:
    """Thread-safe JSONL appender. One file per day."""

    def __init__(self, log_dir: Path):
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _file(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._dir / f"prompts-{day}.jsonl"

    def start(self) -> float:
        return time.perf_counter()

    def record(
        self,
        *,
        agent: str,
        model: str,
        tier: str,
        tcro: dict[str, Any],
        response: str,
        usage: dict[str, int],
        started: float,
        provider: str = "anthropic",
        ok: bool = True,
        error: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> PromptRecord:
        rec = PromptRecord(
            id=uuid.uuid4().hex[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent=agent,
            model=model,
            tier=tier,
            provider=provider,
            tcro=tcro,
            response=response,
            usage=usage,
            cost_usd=_cost(model, usage, provider),
            latency_ms=int((time.perf_counter() - started) * 1000),
            ok=ok,
            error=error,
            tags=tags or {},
        )
        line = json.dumps(asdict(rec), ensure_ascii=False)
        with self._lock:
            with self._file().open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return rec

    def load_all(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for f in sorted(self._dir.glob("prompts-*.jsonl")):
            for ln in f.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    rows.append(json.loads(ln))
        return rows