"""Benchmark: qwen (Ollama) vs Claude on the real OmniTest-AI agent tasks.

Covers two suites, each running its production agent prompt over labelled cases:

    • email  -> EmailAnalyzerAgent.verify   (CHEAP tier)
    • api    -> ApiValidatorAgent.assess     (BALANCED tier)

For each suite + provider it reports:
    • accuracy   — agreement with the human ground-truth label
    • invalid    — responses that weren't parseable JSON (local models fail more)
    • latency    — average wall-clock per call
    • cost       — total USD (local = $0)
    • agreement  — how often the two models gave the same verdict

Use it to decide whether a local model is good enough to take a tier before you
flip OMNI_PROVIDER_CHEAP / OMNI_PROVIDER_BALANCED to `ollama`.

Run:
    python -m scripts.benchmark_llms                    # both suites, Claude vs qwen
    python -m scripts.benchmark_llms --suite api        # one suite only
    python -m scripts.benchmark_llms --skip-claude      # local only (offline)
    python -m scripts.benchmark_llms --qwen-model qwen2.5:14b

Prereqs: local side needs `ollama serve` + `ollama pull <model>`; Claude side
needs subscription login (`claude`) or ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import csv
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.table import Table

from omnitest.ai.client import AIClient, Tier
from omnitest.ai.tracker import PromptTracker
from omnitest.ai.agents.email_analyzer import EmailAnalyzerAgent
from omnitest.ai.agents.api_validator import ApiValidatorAgent

console = Console()


# ── Datasets (ground truth = what a human QA would say) ──────────────────────
@dataclass(frozen=True)
class EmailCase:
    subject: str
    body: str
    expectation: str
    expected_pass: bool


@dataclass(frozen=True)
class ApiCase:
    status: int
    response_json: str
    expectation: str
    expected_pass: bool


EMAIL_CASES: list[EmailCase] = [
    EmailCase("Welcome to Acme",
              "Hi Sam, thanks for signing up! Click Verify Email to activate your account, "
              "then log in to get started.",
              "the email welcomes the user and explains how to get started", True),
    EmailCase("Password reset",
              "We received a request to reset your password. Use this link within 30 minutes: "
              "https://acme.test/reset?t=abc. If you didn't ask, ignore this.",
              "the email provides a password reset link and an expiry", True),
    EmailCase("Your order #4471",
              "Your order has shipped and will arrive Tuesday. Track it: https://acme.test/track/4471.",
              "the email confirms the order shipped and gives tracking", True),
    EmailCase("Your OTP code",
              "Your one-time code is 559102. It expires in 5 minutes.",
              "the email contains a one-time passcode", True),
    EmailCase("Invoice attached",
              "Please find your March invoice attached. Total due: $128.40, payable by Mar 31.",
              "the email states the amount due and a due date", True),
    EmailCase("Welcome to Acme",
              "Hi Sam, thanks for signing up!",
              "the email welcomes the user and explains how to get started", False),
    EmailCase("Password reset",
              "We received a request to reset your password. Our team will contact you shortly.",
              "the email provides a password reset link and an expiry", False),
    EmailCase("Newsletter",
              "Check out our 5 favourite productivity tips this month!",
              "the email contains a one-time passcode", False),
    EmailCase("Your order #4471",
              "Thanks for your order! We'll email you again once it ships.",
              "the email confirms the order shipped and gives tracking", False),
    EmailCase("Meeting notes",
              "Notes from today's sync are in the shared drive.",
              "the email states an invoice amount due and a due date", False),
]

API_CASES: list[ApiCase] = [
    ApiCase(201, '{"id":42,"name":"Sam Lee","email":"sam@acme.test","created_at":"2026-01-02T10:00:00Z"}',
            "a user was created with an id and the email echoes the request", True),
    ApiCase(200, '{"status":"ok","version":"1.4.2"}',
            "the health endpoint reports the service is up", True),
    ApiCase(200, '{"items":[{"id":1},{"id":2}],"total":2,"page":1}',
            "a paginated list with a total count", True),
    ApiCase(404, '{"error":"user not found","code":"USER_NOT_FOUND"}',
            "a not-found error with a clear message", True),
    ApiCase(422, '{"errors":[{"field":"email","message":"invalid email"}]}',
            "a validation error identifying the offending field", True),
    # ── these should FAIL the expectation ──
    ApiCase(201, '{"id":42,"name":"Sam Lee"}',
            "a user was created with an id and the email echoes the request", False),
    ApiCase(200, '{"status":"degraded","version":"1.4.2"}',
            "the health endpoint reports the service is up", False),
    ApiCase(200, '{"items":[],"total":0}',
            "a non-empty paginated list of users", False),
    ApiCase(500, '{"error":"internal server error"}',
            "a successful response containing user data", False),
    ApiCase(200, '{"id":42,"email":"sam@acme.test"}',
            "an error response explaining the request was unauthorized", False),
]


# ── Suite abstraction: task name, tier, agent, per-case runner ───────────────
@dataclass
class Suite:
    name: str
    tier: Tier
    agent_cls: type
    run_case: Callable          # (agent, case) -> bool | None
    cases: list
    claude_model: str
    labels: list[bool] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.labels = [c.expected_pass for c in self.cases]


def _email_run(agent: EmailAnalyzerAgent, c: EmailCase) -> bool | None:
    r = agent.verify(subject=c.subject, body=c.body, expectation=c.expectation)
    return bool(r.get("pass")) if isinstance(r, dict) else None


def _api_run(agent: ApiValidatorAgent, c: ApiCase) -> bool | None:
    r = agent.assess(response_json=c.response_json, expectation=c.expectation, status=c.status)
    return bool(r.get("pass")) if isinstance(r, dict) else None


@dataclass
class Outcome:
    verdict: bool | None
    correct: bool
    latency_ms: int
    cost_usd: float


def _make_client(tier: Tier, provider: str, model: str, log_dir: Path) -> AIClient:
    """Client with the suite's tier pinned to one provider/model; isolated tracker."""
    client = AIClient()
    client._tracker = PromptTracker(log_dir)     # isolate cost/latency capture
    client._routes[tier] = (provider, model)     # pin only the tier this suite uses
    return client


def run_suite_provider(suite: Suite, label: str, provider: str, model: str) -> list[Outcome] | None:
    log_dir = Path(tempfile.mkdtemp(prefix=f"bench_{suite.name}_{label}_"))
    client = _make_client(suite.tier, provider, model, log_dir)
    agent = suite.agent_cls(client=client)
    outcomes: list[Outcome] = []

    console.print(f"\n[bold]{suite.name} · {label}[/bold]  ({provider}/{model})")
    for i, c in enumerate(suite.cases, 1):
        t0 = time.perf_counter()
        try:
            verdict = suite.run_case(agent, c)
        except Exception as exc:  # provider down, HTTP error, or bad JSON
            if i == 1:            # first call failed -> provider unusable, bail
                console.print(f"  [red]unavailable:[/red] {type(exc).__name__}: {exc}")
                return None
            verdict = None
        latency = int((time.perf_counter() - t0) * 1000)

        rec = client.tracker.load_all()[-1]
        correct = verdict is not None and verdict == c.expected_pass
        mark = "✓" if correct else ("?" if verdict is None else "✗")
        console.print(f"  {mark} case {i:2}  verdict={str(verdict):5}  "
                      f"expected={c.expected_pass!s:5}  {latency:5}ms")
        outcomes.append(Outcome(verdict, correct, latency, float(rec.get("cost_usd", 0.0))))
    return outcomes


CSV_HEADER = [
    "timestamp", "suite", "tier", "model", "correct", "total",
    "accuracy", "invalid_json", "avg_latency_ms", "total_cost_usd",
]


def _stats(suite: Suite, outs: list[Outcome]) -> dict:
    n = len(suite.cases)
    correct = sum(o.correct for o in outs)
    return {
        "suite": suite.name,
        "tier": suite.tier.value,
        "correct": correct,
        "total": n,
        "accuracy": round(correct / n, 4) if n else 0.0,
        "invalid_json": sum(o.verdict is None for o in outs),
        "avg_latency_ms": int(sum(o.latency_ms for o in outs) / max(len(outs), 1)),
        "total_cost_usd": round(sum(o.cost_usd for o in outs), 6),
    }


def summarize(suite: Suite, rows: dict[str, list[Outcome]]) -> None:
    table = Table(title=f"{suite.name} — {suite.tier.value} tier", show_lines=True)
    table.add_column("Model")
    table.add_column("Accuracy", justify="right")
    table.add_column("Invalid JSON", justify="right")
    table.add_column("Avg latency", justify="right")
    table.add_column("Total cost", justify="right")

    for label, outs in rows.items():
        s = _stats(suite, outs)
        table.add_row(label, f"{s['correct']}/{s['total']} ({s['accuracy']:.0%})",
                      str(s["invalid_json"]), f"{s['avg_latency_ms']} ms",
                      f"${s['total_cost_usd']:.4f}")
    console.print()
    console.print(table)

    if len(rows) == 2:
        (la, a), (lb, b) = rows.items()
        both = [(x, y) for x, y in zip(a, b) if x.verdict is not None and y.verdict is not None]
        if both:
            agree = sum(x.verdict == y.verdict for x, y in both)
            console.print(f"[bold]Agreement[/bold] {la} vs {lb}: "
                          f"{agree}/{len(both)} ({agree / len(both):.0%})")


def write_csv(path: Path, records: list[dict]) -> None:
    """Append one summary row per (suite, model) run. Header written once."""
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADER)
        if new_file:
            writer.writeheader()
        writer.writerows(records)
    console.print(f"\n[green]Appended {len(records)} row(s) to {path}[/green]")


def build_suites(args) -> list[Suite]:
    all_suites = {
        "email": Suite("email", Tier.CHEAP, EmailAnalyzerAgent, _email_run,
                       EMAIL_CASES, args.claude_email_model),
        "api": Suite("api", Tier.BALANCED, ApiValidatorAgent, _api_run,
                     API_CASES, args.claude_api_model),
    }
    if args.suite == "all":
        return list(all_suites.values())
    return [all_suites[args.suite]]


def main() -> None:
    ap = argparse.ArgumentParser(description="qwen (Ollama) vs Claude benchmark")
    ap.add_argument("--suite", choices=["email", "api", "all"], default="all")
    ap.add_argument("--claude-email-model", default="claude-haiku-4-5")
    ap.add_argument("--claude-api-model", default="claude-sonnet-5")
    ap.add_argument("--qwen-model", default="qwen2.5:7b")
    ap.add_argument("--skip-claude", action="store_true")
    ap.add_argument("--skip-qwen", action="store_true")
    ap.add_argument("--csv", metavar="PATH",
                    help="append summary rows to this CSV for tracking over time")
    ap.add_argument("--min-accuracy", type=float, metavar="FLOAT",
                    help="exit non-zero if any run's accuracy is below this "
                         "(e.g. 0.85). Use in CI or the nightly job.")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    csv_records: list[dict] = []
    any_ran = False
    for suite in build_suites(args):
        rows: dict[str, list[Outcome]] = {}
        if not args.skip_claude:
            r = run_suite_provider(suite, "Claude", "anthropic", suite.claude_model)
            if r is not None:
                rows["Claude"] = r
        if not args.skip_qwen:
            r = run_suite_provider(suite, "qwen", "ollama", args.qwen_model)
            if r is not None:
                rows["qwen"] = r
        if rows:
            summarize(suite, rows)
            any_ran = True
            for label, outs in rows.items():
                model = suite.claude_model if label == "Claude" else args.qwen_model
                csv_records.append({"timestamp": ts, "model": f"{label}:{model}",
                                    **_stats(suite, outs)})

    if not any_ran:
        console.print("\n[red]No providers ran. Check Ollama is up and/or Claude auth.[/red]")
        raise SystemExit(2)
    if args.csv:
        write_csv(Path(args.csv), csv_records)

    # ── threshold gate (CI / nightly alerting) ──
    if args.min_accuracy is not None:
        breaches = [r for r in csv_records if r["accuracy"] < args.min_accuracy]
        if breaches:
            console.print(f"\n[red bold]THRESHOLD BREACH[/red bold] — "
                          f"accuracy below {args.min_accuracy:.0%}:")
            for r in breaches:
                console.print(f"  [red]✗[/red] {r['suite']} · {r['model']}: "
                              f"{r['accuracy']:.0%}")
            raise SystemExit(1)
        console.print(f"\n[green]✓ All runs meet the {args.min_accuracy:.0%} "
                      f"accuracy threshold.[/green]")


if __name__ == "__main__":
    main()
