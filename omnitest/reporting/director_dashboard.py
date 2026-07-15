"""QA Director dashboard — sprint throughput by user story.

Joins three sources by story ID and renders one self-contained HTML page:
  • Allure results  (artifacts/allure-results/*-result.json) → automation + pass/fail
  • Prompt JSONL    (artifacts/prompts/*.jsonl)               → AI calls + cost per story
  • Stories manifest (docs/stories.json, optional)            → planned list, title,
                                                                epic, priority, status

Story IDs flow in via `@pytest.mark.story("OMNI-142")` (Allure label + AI tag).

    python -m omnitest.reporting.director_dashboard

Also appends a daily snapshot to artifacts/reports/director-history.csv so
throughput can be trended over time.
"""
from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from omnitest.ai.tracker import PromptTracker
from omnitest.config import settings

_PRIORITIES = ("P1", "P2", "P3")


# ── data loading ────────────────────────────────────────
def _load_allure(results_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not results_dir.exists():
        return out
    for f in results_dir.glob("*-result.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        labels = {lbl.get("name"): lbl.get("value") for lbl in data.get("labels", [])}
        story = labels.get("story") or labels.get("feature") or labels.get("suite")
        out.append({"story": story, "status": data.get("status", "unknown")})
    return out


def _load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    manifest: dict[str, dict] = {}
    for r in rows:
        sid = r.get("id")
        if sid:
            manifest[sid] = r
    return manifest


# ── aggregation ─────────────────────────────────────────
def _story_state(p: dict) -> tuple[str, str]:
    """Return (label, css-class) describing a story's automation/pass state."""
    if p["tests"] == 0:
        status = (p.get("manifest_status") or "not automated").lower()
        cls = {"in_review": "review", "manual": "manual",
               "backlog": "backlog", "planned": "planned"}.get(status, "none")
        return status.replace("_", " "), cls
    if p["failed"]:
        return "automated · failing", "fail"
    if p["passed"] == p["tests"]:
        return "automated · passing", "pass"
    return "automated · partial", "partial"


def aggregate(allure: list[dict], prompts: list[dict],
              manifest: dict[str, dict]) -> dict[str, dict]:
    per: dict[str, dict] = defaultdict(
        lambda: {"tests": 0, "passed": 0, "failed": 0, "other": 0,
                 "ai_calls": 0, "ai_cost": 0.0, "manifest_status": None}
    )
    for a in allure:
        sid = a["story"] or "(unassigned)"
        p = per[sid]
        p["tests"] += 1
        st = a["status"]
        if st == "passed":
            p["passed"] += 1
        elif st in ("failed", "broken"):
            p["failed"] += 1
        else:
            p["other"] += 1
    for r in prompts:
        sid = (r.get("tags") or {}).get("story")
        if not sid:
            continue
        p = per[sid]
        p["ai_calls"] += 1
        p["ai_cost"] += r.get("cost_usd", 0.0)
    # ensure planned-but-not-yet-tested stories appear, and attach manifest meta
    for sid, meta in manifest.items():
        p = per[sid]
        p["manifest_status"] = meta.get("status")
    return dict(per)


# ── rendering ───────────────────────────────────────────
_CSS = """
:root{--bg:#0d1117;--card:#161b22;--fg:#e6edf3;--mut:#8b949e;--line:#30363d;--acc:#58a6ff}
@media(prefers-color-scheme:light){:root{--bg:#f6f8fa;--card:#fff;--fg:#1f2328;--mut:#636c76;--line:#d0d7de;--acc:#0969da}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{padding:24px 32px;border-bottom:1px solid var(--line)}h1{margin:0;font-size:20px}.sub{color:var(--mut)}
.wrap{max-width:1200px;margin:0 auto;padding:24px 32px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;margin:16px 0 28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.card .n{font-size:24px;font-weight:700}.card .l{color:var(--mut);font-size:12px}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}th{color:var(--mut);font-size:12px}
td.num,th.num{text-align:right}
.pill{font-size:11px;padding:2px 9px;border-radius:20px;white-space:nowrap}
.pill.pass{background:#2ea04333;color:#3fb950}.pill.fail{background:#f8514933;color:#f85149}
.pill.partial{background:#d2992233;color:#d29922}.pill.review{background:#1f6feb33;color:var(--acc)}
.pill.manual{background:#8957e533;color:#a371f7}.pill.backlog,.pill.none,.pill.planned{background:#6e768133;color:var(--mut)}
.prio{font-weight:700}.p1{color:#f85149}.p2{color:#d29922}.p3{color:var(--mut)}
.bar{height:8px;border-radius:6px;background:var(--line);overflow:hidden;margin-top:6px}
.bar>span{display:block;height:100%;background:#3fb950}
"""


def _kpi_cards(per: dict[str, dict], manifest: dict[str, dict]) -> tuple[str, dict]:
    total = len(per)
    automated = sum(1 for p in per.values() if p["tests"] > 0)
    passing = sum(1 for p in per.values() if p["tests"] and not p["failed"]
                  and p["passed"] == p["tests"])
    failing = sum(1 for p in per.values() if p["failed"] > 0)
    execs = sum(p["tests"] for p in per.values())
    passed_execs = sum(p["passed"] for p in per.values())
    cost = sum(p["ai_cost"] for p in per.values())
    cov = f"{automated}/{total} ({automated / total:.0%})" if total else "0"
    pass_rate = f"{passed_execs / execs:.0%}" if execs else "—"

    kpis = {"stories": total, "automated": cov, "passing": passing,
            "failing": failing, "pass rate": pass_rate, "AI cost": f"${cost:.4f}"}
    cards = "".join(
        f'<div class="card"><div class="n">{v}</div><div class="l">{k}</div></div>'
        for k, v in kpis.items()
    )
    snapshot = {"total": total, "automated": automated, "passing": passing,
                "failing": failing, "ai_cost": round(cost, 6)}
    return cards, snapshot


def _priority_table(per: dict[str, dict], manifest: dict[str, dict]) -> str:
    if not manifest:
        return ""
    rows = ""
    for prio in _PRIORITIES:
        ids = [sid for sid, m in manifest.items() if (m.get("priority") or "").upper() == prio]
        if not ids:
            continue
        tot = len(ids)
        auto = sum(1 for sid in ids if per.get(sid, {}).get("tests", 0) > 0)
        pct = auto / tot if tot else 0
        rows += (f'<tr><td class="prio {prio.lower()}">{prio}</td>'
                 f'<td class="num">{auto}/{tot}</td>'
                 f'<td><div class="bar"><span style="width:{pct:.0%}"></span></div></td>'
                 f'<td class="num">{pct:.0%}</td></tr>')
    if not rows:
        return ""
    return ('<h3>Automation coverage by priority</h3>'
            '<table><tr><th>Priority</th><th class="num">Automated</th>'
            f'<th>Coverage</th><th class="num">%</th></tr>{rows}</table>')


def _epic_rollup(per: dict[str, dict], manifest: dict[str, dict]) -> str:
    epics: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "automated": 0, "passing": 0, "failing": 0, "cost": 0.0}
    )
    for sid, p in per.items():
        epic = (manifest.get(sid, {}).get("epic") or "").strip() or "(no epic)"
        e = epics[epic]
        e["total"] += 1
        if p["tests"] > 0:
            e["automated"] += 1
        if p["tests"] and not p["failed"] and p["passed"] == p["tests"]:
            e["passing"] += 1
        if p["failed"]:
            e["failing"] += 1
        e["cost"] += p["ai_cost"]
    # Only worth showing once there's more than one epic (or a real epic name).
    if not epics or (len(epics) == 1 and "(no epic)" in epics):
        return ""
    rows = ""
    for epic, e in sorted(epics.items()):
        pct = e["automated"] / e["total"] if e["total"] else 0
        fail = f'<span class="p1">{e["failing"]}</span>' if e["failing"] else "0"
        rows += (f"<tr><td><b>{html.escape(epic)}</b></td>"
                 f'<td class="num">{e["total"]}</td>'
                 f'<td class="num">{e["automated"]}/{e["total"]}</td>'
                 f'<td><div class="bar"><span style="width:{pct:.0%}"></span></div></td>'
                 f'<td class="num">{pct:.0%}</td>'
                 f'<td class="num">{e["passing"]}</td>'
                 f'<td class="num">{fail}</td>'
                 f'<td class="num">${e["cost"]:.4f}</td></tr>')
    return ('<h3 style="margin-top:28px">By epic</h3>'
            '<table><tr><th>Epic</th><th class="num">Stories</th>'
            '<th class="num">Automated</th><th>Coverage</th><th class="num">%</th>'
            '<th class="num">Passing</th><th class="num">Failing</th>'
            '<th class="num">AI cost</th></tr>' + rows + '</table>')


def _story_rows(per: dict[str, dict], manifest: dict[str, dict]) -> str:
    def sort_key(item):
        sid, p = item
        prio = (manifest.get(sid, {}).get("priority") or "P9").upper()
        return (prio, sid)

    out = ""
    for sid, p in sorted(per.items(), key=sort_key):
        meta = manifest.get(sid, {})
        label, cls = _story_state(p)
        prio = (meta.get("priority") or "").upper()
        prio_html = f'<span class="prio {prio.lower()}">{prio}</span>' if prio else "—"
        title = html.escape(meta.get("title", "") or "")
        epic = html.escape(meta.get("epic", "") or "—")
        typ = html.escape(meta.get("type", "") or "—")
        tests = p["tests"]
        pf = f'{p["passed"]}/{tests}' if tests else "—"
        out += (f"<tr><td><b>{html.escape(sid)}</b><div class='sub'>{title}</div></td>"
                f"<td>{epic}</td><td>{prio_html}</td><td>{typ}</td>"
                f"<td><span class='pill {cls}'>{html.escape(label)}</span></td>"
                f"<td class='num'>{tests or '—'}</td><td class='num'>{pf}</td>"
                f"<td class='num'>{p['ai_calls'] or '—'}</td>"
                f"<td class='num'>${p['ai_cost']:.4f}</td></tr>")
    return out


def _append_snapshot(csv_path: Path, snapshot: dict) -> None:
    header = ["date", "total", "automated", "passing", "failing", "ai_cost"]
    new = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        if new:
            w.writeheader()
        w.writerow({"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), **snapshot})


def build_director_dashboard(out: Path | None = None) -> Path:
    allure = _load_allure(settings.abs_allure_results_dir)
    prompts = PromptTracker(settings.abs_prompt_log_dir).load_all()
    manifest = _load_manifest(settings.abs_stories_manifest)
    per = aggregate(allure, prompts, manifest)

    cards, snapshot = _kpi_cards(per, manifest)
    prio_table = _priority_table(per, manifest)
    epic_table = _epic_rollup(per, manifest)
    rows = _story_rows(per, manifest)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    src = ("manifest" if manifest else "Allure+prompts only (no docs/stories.json)")

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OmniTest-AI · QA Director</title><style>{_CSS}</style></head><body>
<header><h1>OmniTest-AI — QA Director view</h1>
<div class="sub">Sprint throughput by user story · {src} · generated {now}</div></header>
<div class="wrap">
<div class="cards">{cards}</div>
{prio_table}
{epic_table}
<h3 style="margin-top:28px">Stories ({len(per)})</h3>
<table>
<tr><th>Story</th><th>Epic</th><th>Prio</th><th>Type</th><th>State</th>
<th class="num">Tests</th><th class="num">Pass</th><th class="num">AI calls</th><th class="num">AI cost</th></tr>
{rows or '<tr><td colspan="9" class="sub">No stories found. Tag tests with @pytest.mark.story(...) or add docs/stories.json.</td></tr>'}
</table>
</div></body></html>"""

    out = out or (settings._abs(Path("artifacts/reports/director-dashboard.html")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    _append_snapshot(settings._abs(Path("artifacts/reports/director-history.csv")), snapshot)
    return out


if __name__ == "__main__":
    path = build_director_dashboard()
    print(f"Director dashboard written: {path}")
