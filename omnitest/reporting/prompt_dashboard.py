"""Turn the prompt-tracking JSONL into a self-contained HTML dashboard.

    python -m omnitest.reporting.prompt_dashboard

Gives your manager: every prompt (TCRO input) + output, model/tier, tokens,
cost, latency, and roll-ups by agent — no external assets, opens in any browser.
"""
from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from omnitest.ai.tracker import PromptTracker
from omnitest.config import settings


def _summarize(rows: list[dict]) -> dict[str, dict]:  # type: ignore[type-arg]
    agg: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost": 0.0, "in": 0, "out": 0, "ms": 0})
    for r in rows:
        a = agg[r["agent"]]
        a["calls"] += 1
        a["cost"] += r.get("cost_usd", 0.0)
        u = r.get("usage", {})
        a["in"] += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        a["out"] += u.get("output_tokens", 0)
        a["ms"] += r.get("latency_ms", 0)
    return agg


def _row_html(r: dict) -> str:  # type: ignore[type-arg]
    tcro = r.get("tcro", {})
    rules = "".join(f"<li>{html.escape(x)}</li>" for x in tcro.get("rules", []))
    u = r.get("usage", {})
    status = "ok" if r.get("ok", True) else "err"
    return f"""
    <details class="rec {status}">
      <summary>
        <span class="badge {r['tier']}">{html.escape(r['tier'])}</span>
        <b>{html.escape(r['agent'])}</b>
        <code>{html.escape(r['model'])}</code>
        <span class="task">{html.escape(tcro.get('task','')[:90])}</span>
        <span class="meta">${r.get('cost_usd',0):.5f} · {u.get('output_tokens',0)} out · {r.get('latency_ms',0)}ms</span>
      </summary>
      <div class="grid">
        <div><h4>TASK</h4><pre>{html.escape(tcro.get('task',''))}</pre></div>
        <div><h4>CONTEXT</h4><pre>{html.escape(tcro.get('context','')[:2000])}</pre></div>
        <div><h4>RULES</h4><ul>{rules}</ul></div>
        <div><h4>OUTPUT FORMAT</h4><pre>{html.escape(tcro.get('output',''))}</pre></div>
      </div>
      <h4>RESPONSE</h4><pre class="resp">{html.escape(r.get('response','') or r.get('error',''))}</pre>
    </details>"""


_CSS = """
:root{--bg:#0d1117;--card:#161b22;--fg:#e6edf3;--mut:#8b949e;--line:#30363d;--acc:#58a6ff}
@media(prefers-color-scheme:light){:root{--bg:#f6f8fa;--card:#fff;--fg:#1f2328;--mut:#636c76;--line:#d0d7de;--acc:#0969da}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{padding:24px 32px;border-bottom:1px solid var(--line)}h1{margin:0;font-size:20px}.sub{color:var(--mut)}
.wrap{max-width:1100px;margin:0 auto;padding:24px 32px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin:16px 0 28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.card .n{font-size:22px;font-weight:700}.card .l{color:var(--mut);font-size:12px}
.rec{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0;overflow:hidden}
.rec.err{border-color:#f85149}summary{cursor:pointer;padding:12px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
summary::-webkit-details-marker{display:none}.task{color:var(--mut);flex:1;min-width:200px}
.meta{color:var(--mut);font-size:12px}.badge{font-size:11px;padding:2px 8px;border-radius:20px;text-transform:uppercase}
.badge.cheap{background:#1f6feb33;color:var(--acc)}.badge.balanced{background:#8957e533;color:#a371f7}.badge.smart{background:#2ea04333;color:#3fb950}
code{background:#0000001a;padding:1px 6px;border-radius:5px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:0 14px 8px}h4{margin:12px 0 4px;color:var(--mut);font-size:11px;letter-spacing:.05em}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;white-space:pre-wrap;margin:0}
pre.resp{margin:0 14px 14px}table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line)}th{color:var(--mut);font-size:12px}
"""


def build_dashboard(out: Path | None = None) -> Path:
    tracker = PromptTracker(settings.abs_prompt_log_dir)
    rows = tracker.load_all()
    agg = _summarize(rows)
    total_cost = sum(r.get("cost_usd", 0.0) for r in rows)
    total_out = sum(r.get("usage", {}).get("output_tokens", 0) for r in rows)

    cards = "".join(
        f'<div class="card"><div class="n">{v}</div><div class="l">{k}</div></div>'
        for k, v in {
            "prompts": len(rows),
            "agents": len(agg),
            "total cost": f"${total_cost:.4f}",
            "output tokens": f"{total_out:,}",
        }.items()
    )
    table = "".join(
        f"<tr><td>{a}</td><td>{v['calls']}</td><td>${v['cost']:.4f}</td>"
        f"<td>{v['in']:,}</td><td>{v['out']:,}</td>"
        f"<td>{v['ms'] // max(v['calls'],1)}ms</td></tr>"
        for a, v in sorted(agg.items())
    )
    records = "".join(_row_html(r) for r in reversed(rows[-500:]))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OmniTest-AI · Prompt Tracker</title><style>{_CSS}</style></head><body>
<header><h1>OmniTest-AI — Prompt Tracker</h1>
<div class="sub">TCRO input &amp; output audit · generated {now}</div></header>
<div class="wrap">
<div class="cards">{cards}</div>
<h3>By agent</h3>
<table><tr><th>Agent</th><th>Calls</th><th>Cost</th><th>In tok</th><th>Out tok</th><th>Avg latency</th></tr>{table}</table>
<h3 style="margin-top:28px">Prompts ({len(rows)})</h3>
{records or '<p class="sub">No prompts recorded yet.</p>'}
</div></body></html>"""

    out = out or (settings.abs_prompt_log_dir / "dashboard.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out


if __name__ == "__main__":
    path = build_dashboard()
    print(f"Dashboard written: {path}")