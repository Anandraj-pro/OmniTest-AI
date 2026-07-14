# TODO — manual setup steps (do later)

Things that need *your* accounts, secrets, or dashboards — I can't do these for you.
Grouped by area, roughly in priority order.

## 1. Local environment
- [ ] `pip install -r requirements.txt`
- [ ] `python -m playwright install chromium`
- [ ] (local LLM) `ollama serve` and `ollama pull qwen2.5:7b`

## 2. Authentication / secrets (`.env`)
- [ ] Add `ANTHROPIC_API_KEY=sk-ant-...` (from https://console.anthropic.com) — powers the SMART tier.
- [ ] Create a Slack incoming webhook (Slack → Apps → Incoming Webhooks → add to a channel)
      and set `OMNI_SLACK_WEBHOOK_URL=...` — enables benchmark + suite-failure alerts.

## 3. GitHub Pages + Allure report
- [x] Confirm the first workflow run finished — green, `gh-pages` branch created.
- [x] Repo made public + GitHub Pages enabled on the `gh-pages` branch (built, HTTP 200).
      Live at https://anandraj-pro.github.io/OmniTest-AI/
- [x] Set `OMNI_REPORT_BASE_URL=https://anandraj-pro.github.io/OmniTest-AI/` in `.env`
      → the Slack "Open Allure Report" button is wired.

## 4. CI configuration (GitHub Actions)
- [ ] Add repo secret `ANTHROPIC_API_KEY` (Settings → Secrets and variables → Actions)
      so SMART-tier tests can run in CI.
- [ ] Decide whether to widen `pytest -m "smoke"` in `.github/workflows/allure-report.yml`
      (add an Ollama setup step / self-hosted runner if you want the local tiers gated in CI).

## 5. Point the framework at the real app under test
- [ ] Set `OMNI_BASE_URL` and `OMNI_API_BASE_URL` in `.env`.
- [ ] Configure email creds (`OMNI_EMAIL_USER` / `OMNI_EMAIL_PASSWORD`, or the Gmail-API adapter).

## 6. Validate the LLM routing decision
- [ ] With the API key set, run the full head-to-head:
      `python -m scripts.benchmark_llms --csv artifacts/benchmarks/history.csv`
      then `python -m scripts.chart_benchmarks --open`.
- [ ] Expand `EMAIL_CASES` / `API_CASES` in `scripts/benchmark_llms.py` with your own
      trickier real data before trusting a local model on release gates.
- [ ] If qwen2.5:7b underperforms on the `api` (BALANCED) suite, try `qwen2.5:14b`
      and update `OMNI_MODEL_BALANCED` in `.env`.

---
_Reference: full architecture and rationale in [`understanding_doc.md`](understanding_doc.md)._
