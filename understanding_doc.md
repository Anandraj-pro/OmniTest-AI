# OmniTest-AI — Understanding Doc

A plain-language walkthrough of what this framework is, how the pieces fit
together, and *why* each choice was made. Read top-to-bottom once; then drop your
questions in the **Q&A** section at the bottom and I'll answer them inline.

---

## 1. What is OmniTest-AI, in one paragraph?

It's an AI-driven test automation framework. It does four kinds of testing —
**API**, **UI (Playwright)**, **email send/receive**, and **BDD** — and every
place where a human would normally eyeball a result ("does this response make
sense?", "did the email actually contain the right content?", "why did this
selector break?") is handled by a **Claude AI agent** instead. Every AI call is
built from a strict **TCRO** prompt and logged so your manager can audit exactly
what was asked and what came back, with token/cost accounting.

---

## 2. The big picture (layers)

```
┌─────────────────────────────────────────────────────────────┐
│  TESTS  (tests/*.py, tests/bdd/*.feature)                    │  ← what you write
│  pytest + pytest-bdd + Playwright                            │
└───────────────┬─────────────────────────────────────────────┘
                │ uses fixtures from conftest.py
┌───────────────▼─────────────────────────────────────────────┐
│  CAPABILITY LAYER                                            │
│  api/ (httpx)   ui/ (Playwright)   email_/ (SMTP·IMAP·Gmail) │  ← "do the action"
└───────────────┬─────────────────────────────────────────────┘
                │ delegates judgement to
┌───────────────▼─────────────────────────────────────────────┐
│  AI LAYER  (omnitest/ai/)                                    │  ← "make the decision"
│  agents → AIClient (model routing) → TCRO → PromptTracker    │
└───────────────┬─────────────────────────────────────────────┘
                │ every call logged as JSONL
┌───────────────▼─────────────────────────────────────────────┐
│  REPORTING     Allure (test results) + Prompt Dashboard (AI) │  ← "prove what happened"
└─────────────────────────────────────────────────────────────┘
```

Key idea: **the capability layer *acts*, the AI layer *judges*.** An `ApiClient`
sends the HTTP request (deterministic, no AI). The `ApiValidatorAgent` decides
whether the response is semantically correct (AI). Keeping these separate means
your tests stay fast and cheap when they don't need a brain, and only spend
tokens when judgement is actually required.

---

## 3. TCRO — the mandatory prompt shape

Every single AI call is built from a `TCRO` object (`omnitest/ai/tcro.py`).
TCRO = **Task, Context, Rules, Output**:

| Letter | Meaning | Example | Where it goes |
|--------|---------|---------|---------------|
| **T** Task | The specific per-request ask | "Verify this API response represents a created user" | user message |
| **C** Context | Stable domain/system info | "You test a REST API for a banking app…" | **cached** system prompt |
| **R** Rules | Constraints the output must obey | "Only fail on real defects, not cosmetic differences" | **cached** system prompt |
| **O** Output | Exact response format required | "Return JSON `{pass, reason}`" | user message |

**Why split it this way?** Context + Rules are the *same* on every call in a run,
so they're rendered into the `system` prompt with a **cache breakpoint**
(`cache_control: ephemeral`). Claude charges ~10% for cached reads. Only the
varying Task + Output pay full price. That is the single biggest token-saver in
the framework, and it's why TCRO is mandatory rather than optional.

**Why your manager cares:** because every prompt is a structured TCRO object, it
can be logged, displayed, and audited uniformly — no free-form prompt strings
scattered through the code.

---

## 4. Model routing — "powerful but few tokens"

You asked for the most powerful *and* the most token-efficient agents. Those pull
in opposite directions, so the framework routes each job to the **cheapest model
that can actually do it** (`omnitest/ai/client.py`, `Tier` enum):

| Tier | Model | Cost (in/out per 1M) | Used for |
|------|-------|----------------------|----------|
| `CHEAP` | `claude-haiku-4-5` | $1 / $5 | classification, extraction, yes/no email checks |
| `BALANCED` | `claude-sonnet-5` | $3 / $15 | content/context validation, summarizing |
| `SMART` | `claude-opus-4-8` | $5 / $25 | test generation, failure root-cause, self-healing |

Each agent declares its own tier (e.g. `EmailAnalyzerAgent` is CHEAP,
`FailureAnalystAgent` is SMART). So a suite of 100 email checks runs on Haiku,
and only the rare "why did this break?" call spends Opus money. You override tiers
in `.env` (`OMNI_MODEL_*`).

Two more token levers, both applied automatically in `AIClient.run()`:
- **Prompt caching** (section 3) — cached Context+Rules.
- **Adaptive thinking** (`thinking={"type":"adaptive"}`) — the model spends
  reasoning tokens only when the task is hard, nothing when it's trivial.

---

## 5. Prompt tracking — manager visibility

Everything flows through `AIClient.run()`, which after every call writes one line
to a JSONL file (`omnitest/ai/tracker.py`, one file per day
`artifacts/prompts/prompts-YYYY-MM-DD.jsonl`). Each record has:

- agent name, model, tier
- the full TCRO input (task/context/rules/output)
- the response text
- token usage (input, output, cache-read, cache-write) **and computed $ cost**
- timestamp, duration, ok/error

Then `omnitest/reporting/prompt_dashboard.py` turns that JSONL into a
**self-contained HTML dashboard** (light/dark theme, per-agent rollups, every
prompt's input + output). Run it with:

```bash
python -m omnitest.reporting.prompt_dashboard
```

This is the artifact you hand your manager: it answers "what did the AI ask, what
did it answer, and what did it cost?" for every call.

---

## 6. The AI agents (omnitest/ai/agents/)

Each agent is a thin wrapper around `AIClient` with a fixed tier and baseline
rules. They all inherit `BaseAgent.ask(...)` which builds the TCRO for you.

| Agent | Tier | What it decides |
|-------|------|-----------------|
| `TestGeneratorAgent` | SMART | generate Gherkin / Robot suites from a description |
| `ApiValidatorAgent` | BALANCED | is this API response semantically correct? suggest assertions |
| `EmailAnalyzerAgent` | CHEAP | does the email contain/mean the expected content? extract fields |
| `FailureAnalystAgent` | SMART | root-cause a failure; heal a broken selector from the DOM |

---

## 7. Capability layers

### API (`omnitest/api/`)
`ApiClient` (httpx) sends requests and returns an `ApiResponse` with **fluent
assertions**: `.expect_status(200).expect_schema(CreatedUser).expect_path(...)`.
Deterministic checks live here; semantic checks go to `ApiValidatorAgent`.

### UI (`omnitest/ui/`)
`BrowserManager` wraps sync Playwright (tracing on for Allure). `BasePage` has a
`locate(selector, intent, timeout)` method with **AI self-healing**: if a
selector times out, it hands the DOM + your stated *intent* to
`FailureAnalystAgent`, which proposes a working selector. That's why locators
take an `intent` string — it's what the AI uses to re-find the element.

### Email (`omnitest/email_/`)
Adapter pattern so the backend is swappable:
- `SmtpImapClient` — stdlib smtplib/imaplib (default)
- `GmailApiClient` — Gmail API (optional google deps)
- `make_email_client(backend)` — factory, chosen via `OMNI_EMAIL_BACKEND`

Shared logic (`base.py`): `send`, `wait_for` (polls inbox with tenacity),
`verify_content` and `extract` (delegate to `EmailAnalyzerAgent` for semantic
checks — "did the reset email actually explain how to reset?", not just string
matching).

---

## 8. The test layer (what you actually write)

Primary stack: **Playwright + pytest + pydantic**, with **pytest-bdd** for BDD.

- `tests/conftest.py` — fixtures: `api`, `email`, the four AI agents (`api_ai`,
  `email_ai`, `failure_ai`, `gen`), and `ai_page` (wraps Playwright's `page` in a
  self-healing `BasePage`). Also a hook that screenshots to Allure on UI failure.
- `pytest.ini` — markers (`api/ui/email/smoke/ai`), Allure output dir, browser.
- `omnitest/models.py` — pydantic models (`User`, `CreatedUser`, `HealthStatus`)
  for building valid payloads and type-checking responses.

Robot Framework is kept as an **optional** keyword library
(`omnitest/robot/OmniAI.py`), not the primary path.

---

## 9. Supporting pieces

- **Scheduler** (`omnitest/scheduler/`) — APScheduler cron jobs that run suites on
  a schedule and rebuild the prompt dashboard after each run. Includes
  `cron_benchmark(...)` — a nightly LLM quality/cost check that runs the
  benchmark, appends the history CSV, and regenerates the trend chart (see §13.4).
- **Utils** (`omnitest/utils/`) — Rich logger, Faker data factory, tenacity retry.
- **Config** (`omnitest/config/settings.py`) — pydantic-settings; everything is
  env-driven via `.env` (see `.env.example`).

---

## 10. Authentication (important — corrected after testing)

> ⚠️ **Tested finding:** the monthly Claude **subscription does NOT authenticate
> this framework.** The Anthropic Python SDK (`anthropic.Anthropic()`) only
> resolves an **API key** (or an explicit auth-token/credentials object). It does
> *not* read the Claude Code / subscription OAuth session — that session is scoped
> to Claude Code and is not authorized for the raw Messages API. A benchmark run
> confirmed the Claude side fails with *"Could not resolve authentication
> method"* when no API key is present.

**What this means for the two ways to run Claude tiers:**

1. **API key (only reliable option for Claude).** Get one at
   `console.anthropic.com`, put it in `.env` as `ANTHROPIC_API_KEY`. This is
   pay-per-token — but model routing keeps volume (and spend) low because only
   BALANCED/SMART calls hit Claude.
2. **Fully local (no billing at all).** Route every tier to Ollama (see §13).
   qwen2.5:7b already benchmarks well on CHEAP; use a larger local model for
   BALANCED/SMART. This is the only way to honor a strict "no API billing" rule.

The zero-arg subscription path in the code remains as a best-effort fallback, but
**do not rely on it** — treat an API key or local models as the real options.

---

## 11. A day in the life of one AI check

1. Test calls `api.get("/users/1")` → real HTTP, no AI.
2. Test calls `api_ai.assess(response)` → agent builds a TCRO.
3. `AIClient.run()` routes to Sonnet (BALANCED), sends cached Context+Rules +
   fresh Task+Output, with adaptive thinking.
4. Response parsed to `{pass, reason}`; test asserts on it.
5. The whole exchange (TCRO + response + tokens + cost) is appended to today's
   JSONL.
6. `prompt_dashboard.py` later renders it into the manager-facing HTML report.

---

## 12. Team & Sprint Playbook

**Scenario:** 4-person QA team — 2 functional QA, 1 automation engineer, 1 lead
(functional + automation) — running a **2-week sprint with 50–55 stories**. Goal:
accelerate throughput without merging untrustworthy tests.

### 12.1 The math (what "fast enough" means)

50–55 stories ÷ 10 working days = **~5–5.5 stories/day for the team**
(≈ 1.3 stories/person/day). That's roughly **2× the earlier 25–30 baseline**
(~3/day). It's only reachable if the team stops doing the slow, repetitive work:
writing test cases from scratch, hand-writing selectors/assertions, fixing broken
locators, and eyeballing API/email content. Those four are exactly what the AI
layer automates — and they scale for free as volume doubles.

> **The catch:** the parts AI *can't* do — acceptance-criteria writing and test
> review — double too, and become your real bottleneck. Hitting 50–55 is a
> process problem (industrialize the human parts), not an "add more AI" problem.
> See **12.7**.

> **Principle:** Humans own *judgement and edge cases*; the framework owns
> *drafting and maintenance*.

### 12.2 Role split

| Person | Primary job this sprint | Framework leverage |
|--------|------------------------|--------------------|
| **Lead** (both skills) | Owns the framework, reviews AI-generated tests, unblocks, takes the 2–3 gnarly stories | `TestGeneratorAgent`, prompt dashboard for oversight |
| **Automation engineer** | Converts approved Gherkin → runnable pytest/Playwright; maintains fixtures | `ai_page` self-healing, `conftest` fixtures |
| **Functional QA #1** | Writes acceptance criteria → feeds `TestGeneratorAgent` → reviews drafts; exploratory on complex stories | `gen.gherkin()`, `ApiValidatorAgent` |
| **Functional QA #2** | Same, splits the backlog; owns email + API semantic validation | `EmailAnalyzerAgent`, `ApiValidatorAgent` |

**The unlock:** your two functional QAs stop being "manual only." With
`TestGeneratorAgent` they produce automatable Gherkin from acceptance criteria
without writing Python — the automation engineer + lead convert the approved ones.
This roughly doubles effective automation throughput.

### 12.3 Accelerators mapped to real sprint pain

1. **Test authoring (biggest win).** Feed each story's acceptance criteria to
   `TestGeneratorAgent.gherkin()` → draft `.feature` files in seconds. QA reviews
   and edits instead of writing from a blank page. ~30 min/story → ~5 min.
2. **Selector maintenance → near zero.** `ai_page` (self-healing `BasePage`)
   re-finds elements from your stated `intent` when the UI shifts. This is where
   automation sprints usually bleed time.
3. **Assertions you don't hand-write.** `ApiValidatorAgent.suggest_assertions()`
   proposes checks from a response; `EmailAnalyzerAgent.verify()` does semantic
   email validation. QA validates *intent*, not every field.
4. **Cost + oversight for the lead.** The prompt dashboard
   (`python -m omnitest.reporting.prompt_dashboard`) shows every AI-generated test
   and its token cost — review at a glance instead of reading every diff.
5. **Scheduler = free regression.** Point APScheduler at the growing suite to run
   nightly. New stories get covered; yesterday's stories stay covered — no human
   time.

### 12.4 Sprint cadence

- **Day 1–2 (planning):** Lead + QAs write/clean acceptance criteria for all
  50–55 stories using a shared AC template (see 12.7). This is the one thing AI
  can't do for you and it's what makes generation good. *Garbage ACs → garbage
  tests.* At this volume, tier stories P1/P2/P3 here too.
- **Day 2–7 (build):** Batch-generate Gherkin → QA reviews → automation
  engineer/lead wire steps (reusing the shared step library) → merge. Split the
  backlog four ways to parallelize.
- **Day 3 onward:** Nightly scheduled regression (mandatory at this volume);
  triage failures each morning — self-healing has already fixed the trivial
  breakages.
- **Day 8–10:** Point humans at the P1 complex/exploratory stories — the
  framework has absorbed the routine deterministic bulk.

### 12.5 Per-story workflow (copy-paste checklist for QA)

```
[ ] 1. Story has clear, testable acceptance criteria (AC). If not, fix first.
[ ] 2. Generate draft:   gen.gherkin(story_description + AC)  →  tests/bdd/features/<story>.feature
[ ] 3. Review the draft — trim hallucinated steps, add missing edge cases.
[ ] 4. Wire step defs (automation eng / lead) using conftest fixtures:
         - API story   → `api` + `api_ai`  (+ pydantic model from omnitest/models.py)
         - UI story    → `ai_page` (self-healing)
         - Email story → `email` + `email_ai`
[ ] 5. Run locally:      pytest -m <marker> tests/...   (markers: api/ui/email/smoke/ai)
[ ] 6. Check the prompt dashboard — confirm AI calls/cost look sane.
[ ] 7. Merge → it joins the nightly scheduled regression automatically.
```

### 12.6 Honest constraints (set expectations with your manager)

- **AI-generated tests still need human review.** Don't merge blind. The speedup
  is "review a draft" vs "write from scratch," not "no humans."
- **Good acceptance criteria are the fuel.** Generation quality tracks AC quality.
  Invest Day 1–2 there.
- **Fully automating 50–55 stories in one sprint is not realistic.** A realistic
  target: automate the ~60–70% that are deterministic UI/API/email flows this
  sprint; smoke-cover + manually test the rest; backlog the long tail. Still a
  large jump over manual.

### 12.7 Scaling from ~30 to 50–55 stories: what has to change

Doubling volume with the **same 4 people and same 10 days** is a process problem,
not a capacity problem. The AI drafting/maintenance scales for free; the human
parts (AC writing, review) double and become the bottleneck. Five changes make it
work:

1. **AC templates + batch generation.** You can't hand-craft 55 ACs one at a time.
   Standardize an AC template, then batch-feed them to `TestGeneratorAgent` in one
   pass rather than story-by-story.
2. **Reusable step library.** Build a shared `tests/bdd/steps/common_steps.py` so
   ~60% of Gherkin steps are already wired — new stories mostly *reuse* steps
   instead of writing fresh ones. This is the single biggest multiplier at volume.
3. **Risk-based prioritization (non-negotiable).** Tier every story:
   - **P1** — automate this sprint (deterministic, high-value flows)
   - **P2** — smoke test + manual this sprint, automate next
   - **P3** — manual / backlog
   Automate the deterministic 60–70%; don't pretend the rest fits in 10 days.
4. **Reviewer rotation.** Test review is now the constraint. Lead + one QA
   dedicate fixed daily blocks purely to reviewing AI drafts so review never
   stalls behind other work.
5. **Nightly regression is mandatory.** At 50–55 stories/sprint the suite grows
   fast; the scheduler carrying regression is what keeps humans free for new work.

> **Bottom line:** the framework absorbs the 2× drafting load automatically. To
> hit 50–55 you industrialize AC-writing and review, and you *prioritize ruthlessly*
> — coverage of the highest-risk 60–70% beats shallow coverage of all 55.

### 12.8 Enablers shipped (concrete files)

The two things that make 50–55 achievable are now scaffolded:

| File | Purpose |
|------|---------|
| `tests/bdd/steps/common_steps.py` | Reusable API/UI/email steps. Most new features need **zero** new Python. |
| `tests/bdd/features/user_signup.feature` | Example proving a feature can be written entirely from existing steps. |
| `tests/bdd/conftest.py` | Registers the shared steps for every feature. |
| `tests/bdd/test_features.py` | Auto-binds every `.feature` → drop a file in, it's collected. |
| `docs/acceptance_criteria_template.md` | The AC template QAs fill and feed to `TestGeneratorAgent`. |

Run the BDD layer:  `pytest tests/bdd -m smoke`

---

## 13. Local & Hybrid LLMs (Ollama)

You don't have to run everything on Claude. The framework now has a **provider
layer** so each routing tier can point at Claude *or* a local Ollama model
(e.g. `qwen2.5:7b`) — free, on your own machine. Agents, TCRO, and tracking are
unchanged; only the `(provider, model)` a tier maps to changes.

### 13.1 How it works

`omnitest/ai/providers/` defines a `Provider` protocol and two implementations:

- `AnthropicProvider` — Claude (prompt cache, adaptive thinking, streaming).
- `OllamaProvider` — local, via Ollama's `/api/chat` over httpx.

`AIClient` routes each `Tier` to a `(provider, model)` pair from settings. The
tracker records the provider and logs **cost $0** for local calls.

### 13.2 The hybrid strategy (recommended)

Run the **high-volume, low-judgement** work locally for free; keep the **hard
judgement** on Claude:

| Tier | Provider / model | Why |
|------|------------------|-----|
| CHEAP | `ollama` / `qwen2.5:7b` | email checks, extraction, classification — huge volume, simple → free & local |
| BALANCED | `anthropic` / `claude-sonnet-5` | content/context validation — needs reliability |
| SMART | `anthropic` / `claude-opus-4-8` | test generation, self-healing — needs the strongest model |

Enable it in `.env`:

```bash
OMNI_PROVIDER_CHEAP=ollama
OMNI_MODEL_CHEAP=qwen2.5:7b
# prereqs: `ollama serve` and `ollama pull qwen2.5:7b`
```

That single change moves your biggest-volume AI calls to $0 without touching a
line of test code.

### 13.3 Upgrade / expand / "merge" path

Your instinct to grow the local side is right — here's the sensible progression:

1. **Start:** `qwen2.5:7b` on CHEAP only. Measure quality on real email/API
   checks via the prompt dashboard (it shows every local response).
2. **Upgrade the local model:** if 7b misses, bump to `qwen2.5:14b` or
   `qwen2.5:32b` (one env var). No code change.
3. **Promote tiers:** once the local model proves reliable on CHEAP, move
   BALANCED to it too; keep only SMART on Claude. This is the cost curve you want.
4. **Add a provider** (not "merge" models — that's model training, out of scope):
   to support vLLM, LM Studio, or an OpenAI-compatible endpoint, add one file in
   `omnitest/ai/providers/` and register it in `make_provider()`. Everything else
   is untouched.
5. **Fine-tune later (optional):** if you want a local model specialized to your
   domain, fine-tune qwen on your own passed/failed examples and point the same
   env var at it. That's the real "enhance existing LLM" move.

> **Note on "merging LLMs":** true model merging (weight averaging) is a training
> activity, not something a test framework does at runtime. The framework's job is
> **routing** — sending each task to the best available model. That gives you 95%
> of the benefit with none of the training cost. Reach for fine-tuning only if
> routing + a bigger local model still isn't enough.

### 13.4 Benchmark before you switch: `scripts/benchmark_llms.py`

Don't flip a tier to local on faith — measure it. This script runs **labelled
cases through the real agent prompts**, once per provider, for two suites:

| Suite | Agent / tier | What it tests |
|-------|--------------|---------------|
| `email` | `EmailAnalyzerAgent.verify` (CHEAP) | semantic email content checks |
| `api` | `ApiValidatorAgent.assess` (BALANCED) | semantic API-response validation |

It reports accuracy vs ground truth, invalid-JSON rate, latency, cost, and
cross-model agreement — per suite.

```bash
python -m scripts.benchmark_llms                     # both suites, Claude vs qwen
python -m scripts.benchmark_llms --suite api         # one suite only
python -m scripts.benchmark_llms --skip-claude       # local only (offline)
python -m scripts.benchmark_llms --qwen-model qwen2.5:14b   # bigger local model
python -m scripts.benchmark_llms --csv artifacts/benchmarks/history.csv  # track over time
```

`--csv` appends one summary row per (suite, model) run — columns: `timestamp,
suite, tier, model, correct, total, accuracy, invalid_json, avg_latency_ms,
total_cost_usd`. Point every run at the same file to build a history.

**Chart that history** with `scripts/chart_benchmarks.py` — a self-contained HTML
page (inline SVG, no matplotlib/CDN, opens offline, light/dark aware) with three
trend charts: accuracy, latency, cost, one line per (suite, model) series.

```bash
python -m scripts.chart_benchmarks --open     # build + open in browser
python -m scripts.chart_benchmarks --csv artifacts/benchmarks/history.csv \
                                   --out artifacts/benchmarks/history.html
```

**One-command loop** — `scripts/bench_and_chart.sh` runs the benchmark (appending
to the CSV) then regenerates the chart. Extra args pass through to the benchmark:

```bash
scripts/bench_and_chart.sh                    # both suites, Claude vs qwen
scripts/bench_and_chart.sh --skip-claude      # local only
OPEN=1 scripts/bench_and_chart.sh             # also open the chart
CSV=... HTML=... scripts/bench_and_chart.sh   # override output paths
```

**Run it nightly** — the scheduler has a dedicated job that runs the benchmark and
regenerates the chart on a cron schedule (default 02:30). It degrades gracefully:
whichever provider is available runs, the missing one is skipped.

```python
from omnitest.scheduler import TestScheduler
sched = TestScheduler(background=True)
sched.cron_benchmark(cron="30 2 * * *")                 # both providers
sched.cron_benchmark(cron="30 2 * * *", extra_args=["--skip-claude"])  # local only
sched.start(block=False)
```

**Threshold gate** — the nightly job enforces a minimum accuracy (default **85%**)
and logs a prominent `ERROR` alert if any provider/suite drops below it, catching
a silent local-model regression. Tune or disable it:

```python
sched.cron_benchmark(min_accuracy=0.90)   # stricter
sched.cron_benchmark(min_accuracy=None)    # disable the gate
```

The same gate works standalone for CI (exit 1 on breach, 2 if no provider ran):

```bash
python -m scripts.benchmark_llms --min-accuracy 0.85   # non-zero exit fails the build
```

**Slack alert on breach** — set `OMNI_SLACK_WEBHOOK_URL` in `.env` and a breach
pings your channel (in addition to the `ERROR` log). The message lists the exact
failing series, read structured from the history CSV:

```
🚨 OmniTest-AI benchmark below 95% threshold
• api · qwen:qwen2.5:7b: 90% (9/10)
Chart: artifacts/benchmarks/history.html
```

Notifications are best-effort (`omnitest/utils/notify.py`): a no-op if the webhook
is unset, and they never crash the job. Reusable elsewhere via
`from omnitest.utils.notify import notify_slack`.

**Suite-failure alerts** — the same webhook also fires when any scheduled suite
(`cron_robot` / `cron_pytest`) exits non-zero. The message carries the failing
suite name and the pytest/robot summary line. So one webhook covers both signals:
a suite going red, and the local LLM tiers silently regressing below threshold.

**Block Kit "Open Allure Report" button** — both alert types render as Block Kit
(header + section) and include a clickable button to the published Allure report
when `OMNI_REPORT_BASE_URL` is set (e.g. your CI/static host). Slack requires a
real http(s) URL, so if that var is blank the button is simply omitted and the
alert stays text-only — no broken links. `notify_slack(text, blocks=...)` and the
`allure_button(...)` helper (`omnitest/utils/notify.py`) are reusable for any
other alert you add later.

### 13.6 Publishing the Allure report (CI)

`.github/workflows/allure-report.yml` (GitHub Actions) runs the suite and
publishes the Allure report — **with history** — to GitHub Pages on every push,
nightly, or manual dispatch. The resulting URL is what powers the Slack button.

- **One-time setup:** repo → *Settings → Pages* → deploy from the `gh-pages`
  branch. Optionally add secret `ANTHROPIC_API_KEY` to run SMART-tier tests.
- **Report URL:** `https://<owner>.github.io/<repo>/` → put this in
  `OMNI_REPORT_BASE_URL` so the "Open Allure Report" button links to it.
- **History:** the workflow fetches the previous `gh-pages` report and keeps the
  last 30 runs, so Allure shows trends over time.
- **CI caveat:** the CHEAP/BALANCED tiers default to a *local* Ollama that isn't
  present on GitHub runners — the workflow routes those to Claude and runs only
  `-m smoke` by default. Widen the marker (or add an Ollama setup step) to match
  what you actually want gated in CI. `|| true` + `if: always()` guarantee the
  report publishes even when tests fail.

Prereqs: local side needs `ollama serve` + `ollama pull <model>`; Claude side
needs subscription login or `ANTHROPIC_API_KEY`.

**Runs observed** (qwen2.5:7b, local, 10 cases each):

| Suite | Accuracy | Latency | Cost |
|-------|----------|---------|------|
| email (CHEAP) | **10/10** | ~5.5 s/call | $0 |
| api (BALANCED) | **9/10** | ~4.1 s/call | $0 |

**Read:** qwen is solid on the simpler email task, but dropped a case on the
harder API-validation task — exactly why BALANCED is a bigger risk to move local
than CHEAP. Recommendation: **move CHEAP to qwen now; keep BALANCED on Claude**
until a bigger local model (14b/32b) benchmarks clean on the `api` suite. Expand
the `EMAIL_CASES` / `API_CASES` lists with your own trickier real data before
trusting local on release gates.

### 13.5 Trade-offs to keep in mind

- **Quality:** a 7b local model is *not* Opus. Keep it on genuinely simple tasks;
  watch the dashboard for wrong verdicts before promoting it to harder tiers.
- **Throughput:** local inference is limited by your GPU/CPU. For a 50-story
  nightly regression, a local 7b may be slower than the cloud — benchmark first.
- **Consistency:** cloud models are more deterministic across runs. For anything a
  human will trust blindly (release gates), prefer Claude.

---

## 14. Sprint Timeline (how the team + framework run a 2-week sprint)

How a 4-person QA team runs a 2-week sprint (50–55 stories) once OmniTest-AI is
doing the heavy lifting. Shorthand: **L** = Lead (both skills), **AE** =
Automation Engineer, **Q1 / Q2** = Functional QA.

### 14.1 Phase timeline — 10 working days

| Days | Phase | Team focus | What the framework does |
|------|-------|-----------|-------------------------|
| **1–2** | Plan & write ACs | All four write/clean acceptance criteria using `docs/acceptance_criteria_template.md`; tier every story **P1/P2/P3** | — (human-only; AI can't do this) |
| **2–3** | Generate & review | Q1/Q2 feed ACs → `TestGeneratorAgent.gherkin()` → review drafts. L reviews for correctness | Drafts `.feature` files in seconds from ACs |
| **3–7** | Build the bulk | AE + L wire step defs reusing `common_steps.py`; Q1/Q2 keep generating/reviewing next stories | Self-healing `ai_page` absorbs selector churn; CI publishes Allure per push |
| **6–9** | Stabilize | Team triages failures each morning; L + one QA take the P1 complex/exploratory stories | Nightly regression + LLM benchmark run; Slack alerts on any red |
| **9–10** | Sign-off & retro | Regression review, release decision, retro | Allure report = sign-off artifact; prompt dashboard = manager view |

### 14.2 Daily rhythm (every day, not just once)

```
MORNING   → Triage last night's Slack alerts (regression failures + LLM accuracy).
            Self-healing already fixed trivial UI breaks overnight.
STANDUP   → Blockers, story handoffs (AC-writer → step-wirer).
DAY WORK  → Parallel lanes (below).
EVENING   → Nightly scheduler fires: full regression + qwen-vs-Claude benchmark
            → Allure report, prompt dashboard, trend chart all refresh.
```

The key: **the framework works the night shift.** Regression, self-healing,
benchmarks, and reports run while nobody's watching — the team walks in to a
triaged list, not a blank slate.

### 14.3 Parallel lanes (why 50–55 fits)

The four don't work serially on one story — they run a **pipeline**:

```
Q1/Q2:  AC → generate Gherkin → review  ──┐
                                          ├─→  AE/L: wire steps (reuse common_steps) → merge
L:      review drafts, unblock  ──────────┘                                    │
                                                                   nightly regression picks it up
```

While AE wires story #12's steps, Q1 is already reviewing #15's generated Gherkin.
That overlap turns ~3 stories/day (manual) into ~5–5.5/day.

### 14.4 Definition of Done per story

Not "done" until (see §12.5): AC written & tiered → Gherkin generated &
**human-reviewed** → steps wired (reused where possible) → passes locally →
merged → auto-joined nightly regression.

### 14.5 Guardrails

- **Days 1–2 are sacred.** Good ACs are the fuel; rushing them poisons every
  generated test downstream.
- **Target ~60–70% automated this sprint** (deterministic API/UI/email flows).
  Smoke-cover P2, backlog P3 — don't chase 100%.
- **Review is the real bottleneck at this volume**, not authoring. Protect
  L + one QA's review blocks daily.

---

## Q&A (post your questions here)

> Add your questions below and I'll answer each one inline in this file.

**Q1.**

**Q2.**

**Q3.**