# OmniTest-AI

[![Tests & Allure report](https://github.com/Anandraj-pro/OmniTest-AI/actions/workflows/allure-report.yml/badge.svg)](https://github.com/Anandraj-pro/OmniTest-AI/actions/workflows/allure-report.yml)

AI-driven test automation framework — **API + UI (Playwright) + email** testing
where every judgement call (is this response/email correct? why did this break?)
is made by a routed **Claude/local LLM** agent, with full prompt tracking, model
routing for cost control, Allure reporting, and Slack alerting.

> **Full architecture & rationale:** see [`understanding_doc.md`](understanding_doc.md).

## Quickstart

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env          # then edit — see Authentication below
pytest -m smoke               # run the smoke suite
```

### Authentication (important)

The monthly Claude subscription **cannot** authenticate the SDK. Use one of:

- **API key** — set `ANTHROPIC_API_KEY` in `.env` (pay-per-token; routing keeps it low).
- **Local, free** — route tiers to Ollama (`OMNI_PROVIDER_*=ollama`), no key needed.

The default `.env` is a **hybrid**: CHEAP + BALANCED run locally on Ollama ($0),
SMART runs on Claude (needs the key). See §10 and §13 of the understanding doc.

## Key commands

| Command | What it does |
|---------|--------------|
| `pytest -m smoke` | Run the smoke suite (markers: `api ui email smoke ai`) |
| `python -m omnitest.reporting.prompt_dashboard` | Build the manager-facing prompt/cost dashboard |
| `python -m scripts.benchmark_llms` | Benchmark Claude vs local qwen (email + API tasks) |
| `scripts/bench_and_chart.sh` | Benchmark → CSV → regenerate trend chart in one step |

## What's inside

- **AI layer** (`omnitest/ai/`) — TCRO prompts, tier-based model routing
  (Claude/Ollama), JSONL prompt tracking + HTML dashboard.
- **Capabilities** — `api/` (httpx), `ui/` (Playwright, self-healing selectors),
  `email_/` (SMTP·IMAP·Gmail adapters, semantic content checks).
- **Tests** (`tests/`) — pytest + pytest-bdd; reusable step library in
  `tests/bdd/steps/common_steps.py`.
- **Scheduler** (`omnitest/scheduler/`) — nightly suites + LLM benchmark, with
  Slack alerts (accuracy threshold + suite failures) and a Block Kit link button.
- **CI** (`.github/workflows/allure-report.yml`) — runs the suite and publishes
  the Allure report (with history) to GitHub Pages.
