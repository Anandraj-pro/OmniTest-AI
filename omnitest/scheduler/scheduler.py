"""APScheduler-based scheduling for recurring suites (nightly regression, etc.).

    from omnitest.scheduler import TestScheduler
    sched = TestScheduler()
    sched.cron_robot("tests/robot/suites", cron="0 2 * * *", suite_name="nightly")
    sched.cron_pytest("tests/bdd", cron="0 */4 * * *", suite_name="smoke")
    sched.cron_benchmark(cron="30 2 * * *")   # nightly LLM quality/cost check
    sched.start()     # blocking; use start(block=False) for background
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from omnitest.config.settings import PROJECT_ROOT
from omnitest.reporting import build_dashboard
from omnitest.utils.logger import get_logger
from omnitest.utils.notify import allure_button, notify_slack

log = get_logger("scheduler")


def _latest_breaches(csv_path: str, min_accuracy: float) -> list[dict]:
    """Rows from the most recent benchmark run whose accuracy is below threshold."""
    p = PROJECT_ROOT / csv_path
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return []
    latest = max(r["timestamp"] for r in rows)
    return [r for r in rows
            if r["timestamp"] == latest and float(r["accuracy"]) < min_accuracy]


def _alert_slack_breach(csv_path: str, min_accuracy: float) -> None:
    breaches = _latest_breaches(csv_path, min_accuracy)
    lines = [f"• {r['suite']} · {r['model']}: {float(r['accuracy']):.0%} "
             f"({r['correct']}/{r['total']})" for r in breaches]
    body = "\n".join(lines) if lines else "(see benchmark logs for details)"
    fallback = (f":rotating_light: OmniTest-AI benchmark below "
                f"{min_accuracy:.0%} threshold\n{body}")
    blocks: list[dict] = [
        {"type": "header",
         "text": {"type": "plain_text",
                  "text": f":rotating_light: Benchmark below {min_accuracy:.0%}",
                  "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
    ]
    button = allure_button("Open Allure Report")
    if button:
        blocks.append(button)
    notify_slack(fallback, blocks=blocks)


def _run(cmd: list[str], label: str) -> None:
    log.info("[%s] $ %s", label, " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    log.info("[%s] exit=%s", label, proc.returncode)
    if proc.returncode != 0:
        log.warning("[%s] stderr:\n%s", label, proc.stderr[-2000:])
        _alert_slack_suite_failure(label, proc.returncode, proc.stdout, proc.stderr)
    # refresh the manager-facing prompt dashboard after every run
    build_dashboard()


def _alert_slack_suite_failure(label: str, returncode: int,
                               stdout: str, stderr: str) -> None:
    # Prefer the pytest/robot summary line from stdout; fall back to stderr tail.
    tail = (stdout or stderr).strip()[-800:]
    fallback = f":x: OmniTest-AI suite failed: {label} (exit {returncode})"
    blocks: list[dict] = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f":x: Suite failed: {label}"[:150],
                  "emoji": True}},
        {"type": "section",
         "text": {"type": "mrkdwn", "text": f"*Exit code:* `{returncode}`\n```{tail}```"}},
    ]
    button = allure_button("Open Allure Report", style="danger")
    if button:
        blocks.append(button)
    notify_slack(fallback, blocks=blocks)


def _run_benchmark(csv_path: str, html_path: str, suite: str,
                   extra_args: list[str], min_accuracy: float | None) -> None:
    """Run the LLM benchmark (append CSV) then regenerate the trend chart.

    With `min_accuracy`, the benchmark exits 1 on a threshold breach — surfaced
    here as a prominent ERROR alert (exit 2 = no provider ran).
    """
    (PROJECT_ROOT / csv_path).parent.mkdir(parents=True, exist_ok=True)
    bench = [sys.executable, "-m", "scripts.benchmark_llms",
             "--suite", suite, "--csv", csv_path, *extra_args]
    if min_accuracy is not None:
        bench += ["--min-accuracy", str(min_accuracy)]
    proc = subprocess.run(bench, capture_output=True, text=True, cwd=PROJECT_ROOT)
    log.info("[benchmark] exit=%s", proc.returncode)

    if proc.returncode == 1 and min_accuracy is not None:
        # Threshold breach — the actionable alert. stdout carries which series failed.
        log.error("[benchmark] ACCURACY BELOW %.0f%% THRESHOLD:\n%s",
                  min_accuracy * 100, proc.stdout[-2000:])
        _alert_slack_breach(csv_path, min_accuracy)   # ping the team
    elif proc.returncode != 0:
        log.warning("[benchmark] non-zero exit:\n%s", proc.stderr[-2000:])

    chart = [sys.executable, "-m", "scripts.chart_benchmarks",
             "--csv", csv_path, "--out", html_path]
    subprocess.run(chart, capture_output=True, text=True, cwd=PROJECT_ROOT)
    log.info("[benchmark] chart -> %s", html_path)


class TestScheduler:
    def __init__(self, *, background: bool = False) -> None:
        self._sched = BackgroundScheduler() if background else BlockingScheduler()

    def cron_robot(self, suite_path: str, *, cron: str, suite_name: str,
                   output_dir: str = "artifacts/robot") -> None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-m", "robot",
               "--listener", "allure_robotframework;artifacts/allure-results",
               "-d", output_dir, suite_path]
        self._sched.add_job(_run, CronTrigger.from_crontab(cron),
                            args=[cmd, suite_name], id=f"robot:{suite_name}",
                            replace_existing=True)
        log.info("scheduled robot suite %r (%s)", suite_name, cron)

    def cron_pytest(self, test_path: str, *, cron: str, suite_name: str) -> None:
        cmd = [sys.executable, "-m", "pytest", test_path,
               "--alluredir", "artifacts/allure-results"]
        self._sched.add_job(_run, CronTrigger.from_crontab(cron),
                            args=[cmd, suite_name], id=f"pytest:{suite_name}",
                            replace_existing=True)
        log.info("scheduled pytest suite %r (%s)", suite_name, cron)

    def cron_benchmark(
        self,
        *,
        cron: str = "30 2 * * *",
        suite: str = "all",
        csv_path: str = "artifacts/benchmarks/history.csv",
        html_path: str = "artifacts/benchmarks/history.html",
        extra_args: list[str] | None = None,
        min_accuracy: float | None = 0.85,
        suite_name: str = "llm-benchmark",
    ) -> None:
        """Nightly LLM quality/cost check: benchmark providers, append CSV, chart.

        Degrades gracefully — if Claude has no API key or Ollama is down, the
        available provider still runs and the missing one is skipped.

        `min_accuracy` (default 0.85) logs a prominent ERROR alert if any
        provider/suite drops below it — catches a silent local-model regression.
        Pass `min_accuracy=None` to disable the gate.
        """
        self._sched.add_job(
            _run_benchmark, CronTrigger.from_crontab(cron),
            args=[csv_path, html_path, suite, extra_args or [], min_accuracy],
            id=f"benchmark:{suite_name}", replace_existing=True,
        )
        log.info("scheduled LLM benchmark %r (%s)", suite_name, cron)

    def start(self, *, block: bool = True) -> None:
        log.info("scheduler starting (%d jobs)", len(self._sched.get_jobs()))
        if block and isinstance(self._sched, BlockingScheduler):
            self._sched.start()
        else:
            self._sched.start()

    def shutdown(self) -> None:
        self._sched.shutdown(wait=False)