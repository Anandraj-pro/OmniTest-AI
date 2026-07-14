"""Chart the benchmark history CSV as a self-contained HTML page (no deps).

Reads the CSV produced by `benchmark_llms.py --csv <file>` and renders three
line charts — accuracy, latency, cost — one line per (suite, model) series,
so you can see trends as you tune local models or swap Claude versions.

Pure-Python inline SVG: no matplotlib, no CDN, opens offline. Light/dark aware,
matching the prompt dashboard.

Run:
    python -m scripts.chart_benchmarks                                   # defaults
    python -m scripts.chart_benchmarks --csv artifacts/benchmarks/history.csv \
                                       --out artifacts/benchmarks/history.html
"""
from __future__ import annotations

import argparse
import csv
import html
import webbrowser
from collections import defaultdict
from pathlib import Path

# Distinct, colour-blind-friendly palette assigned per series.
_PALETTE = ["#2563eb", "#dc2626", "#059669", "#d97706",
            "#7c3aed", "#0891b2", "#db2777", "#65a30d"]

_W, _H = 820, 300
_ML, _MR, _MT, _MB = 64, 170, 34, 46   # margins (right leaves room for legend)


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _series(rows: list[dict], metric: str) -> dict[str, list[tuple[int, float]]]:
    """{'suite · model': [(x_index, value), ...]} ordered by run timestamp."""
    timestamps = sorted({r["timestamp"] for r in rows})
    x_of = {ts: i for i, ts in enumerate(timestamps)}
    out: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for r in rows:
        key = f"{r['suite']} · {r['model']}"
        try:
            out[key].append((x_of[r["timestamp"]], float(r[metric])))
        except (KeyError, ValueError):
            continue
    for k in out:
        out[k].sort(key=lambda p: p[0])
    return dict(out)


def _svg_chart(title: str, series: dict[str, list[tuple[int, float]]],
               fmt, y_min: float | None = None, y_max: float | None = None) -> str:
    all_y = [y for pts in series.values() for _, y in pts]
    if not all_y:
        return f'<div class="chart"><h3>{html.escape(title)}</h3><p>No data.</p></div>'

    ymin = 0.0 if y_min is None else y_min
    ymax = (max(all_y) * 1.15 or 1.0) if y_max is None else y_max
    if ymax == ymin:
        ymax = ymin + 1
    xs = sorted({x for pts in series.values() for x, _ in pts})
    xmin, xmax = min(xs), max(xs)
    xspan = (xmax - xmin) or 1
    pw, ph = _W - _ML - _MR, _H - _MT - _MB

    def px(x: float) -> float:
        return _ML + (x - xmin) / xspan * pw

    def py(y: float) -> float:
        return _MT + (1 - (y - ymin) / (ymax - ymin)) * ph

    parts: list[str] = [f'<div class="chart"><h3>{html.escape(title)}</h3>',
                        f'<svg viewBox="0 0 {_W} {_H}" role="img">']

    # y grid + labels (5 ticks)
    for i in range(5):
        yv = ymin + (ymax - ymin) * i / 4
        yy = py(yv)
        parts.append(f'<line class="grid" x1="{_ML}" y1="{yy:.1f}" '
                     f'x2="{_ML + pw}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="axis" x="{_ML - 8}" y="{yy + 4:.1f}" '
                     f'text-anchor="end">{fmt(yv)}</text>')

    # x axis labels (run index)
    for x in xs:
        parts.append(f'<text class="axis" x="{px(x):.1f}" y="{_MT + ph + 20}" '
                     f'text-anchor="middle">run {x + 1}</text>')

    # one polyline + points per series
    for i, (label, pts) in enumerate(sorted(series.items())):
        colour = _PALETTE[i % len(_PALETTE)]
        coords = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in pts)
        if len(pts) > 1:
            parts.append(f'<polyline fill="none" stroke="{colour}" '
                         f'stroke-width="2" points="{coords}"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3.5" '
                         f'fill="{colour}"><title>{html.escape(label)}: '
                         f'{fmt(y)}</title></circle>')
        # legend entry
        ly = _MT + 6 + i * 20
        parts.append(f'<rect x="{_W - _MR + 12}" y="{ly}" width="12" height="12" '
                     f'rx="2" fill="{colour}"/>')
        parts.append(f'<text class="legend" x="{_W - _MR + 30}" y="{ly + 11}">'
                     f'{html.escape(label)}</text>')

    parts.append("</svg></div>")
    return "".join(parts)


_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>OmniTest-AI · Benchmark history</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{ --bg:#ffffff; --fg:#111827; --muted:#6b7280; --card:#f9fafb;
           --border:#e5e7eb; --grid:#e5e7eb; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0b0f19; --fg:#e5e7eb; --muted:#9ca3af; --card:#111827;
             --border:#1f2937; --grid:#1f2937; }}
  }}
  body {{ margin:0; padding:2rem; background:var(--bg); color:var(--fg);
          font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }}
  h1 {{ font-size:1.4rem; margin:0 0 .25rem; }}
  .sub {{ color:var(--muted); margin:0 0 1.5rem; }}
  .chart {{ background:var(--card); border:1px solid var(--border);
            border-radius:12px; padding:1rem 1.25rem; margin-bottom:1.25rem; }}
  .chart h3 {{ margin:0 0 .5rem; font-size:1rem; }}
  svg {{ width:100%; height:auto; }}
  .grid {{ stroke:var(--grid); stroke-width:1; }}
  .axis {{ fill:var(--muted); font-size:11px; }}
  .legend {{ fill:var(--fg); font-size:12px; }}
</style>
<body>
  <h1>Benchmark history</h1>
  <p class="sub">{n} runs · source: {src}</p>
  {charts}
</body></html>"""


def build(csv_path: Path, out_path: Path) -> Path:
    rows = _read(csv_path)
    charts = "".join([
        _svg_chart("Accuracy (higher is better)", _series(rows, "accuracy"),
                   fmt=lambda v: f"{v:.0%}", y_min=0.0, y_max=1.0),
        _svg_chart("Avg latency ms (lower is better)", _series(rows, "avg_latency_ms"),
                   fmt=lambda v: f"{v:.0f}"),
        _svg_chart("Total cost USD (lower is better)", _series(rows, "total_cost_usd"),
                   fmt=lambda v: f"${v:.4f}"),
    ])
    n_runs = len({r["timestamp"] for r in rows})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _PAGE.format(n=n_runs, src=html.escape(str(csv_path)), charts=charts),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Chart benchmark history CSV -> HTML")
    ap.add_argument("--csv", default="artifacts/benchmarks/history.csv",
                    type=Path, help="history CSV from benchmark_llms.py --csv")
    ap.add_argument("--out", default="artifacts/benchmarks/history.html",
                    type=Path, help="output HTML path")
    ap.add_argument("--open", action="store_true", help="open the page in a browser")
    args = ap.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"No CSV at {args.csv}. Run: "
                         f"python -m scripts.benchmark_llms --csv {args.csv}")
    out = build(args.csv, args.out)
    print(f"Wrote {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
