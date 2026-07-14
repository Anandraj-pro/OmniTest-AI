#!/usr/bin/env bash
# Run the LLM benchmark, append to history CSV, then regenerate the HTML chart.
#
# Usage:
#   scripts/bench_and_chart.sh                       # both suites, Claude vs qwen
#   scripts/bench_and_chart.sh --skip-claude         # local only (offline)
#   scripts/bench_and_chart.sh --suite api --qwen-model qwen2.5:14b
#   OPEN=1 scripts/bench_and_chart.sh                # also open the chart in a browser
#
# Any extra args are forwarded to benchmark_llms.py.
# Override paths with CSV=... HTML=... env vars.
set -euo pipefail

# Resolve repo root (parent of this script's dir) so it works from anywhere.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CSV="${CSV:-artifacts/benchmarks/history.csv}"
HTML="${HTML:-artifacts/benchmarks/history.html}"

echo "▶ Benchmarking (csv=$CSV) ..."
python -m scripts.benchmark_llms --csv "$CSV" "$@"

echo "▶ Charting -> $HTML ..."
if [ "${OPEN:-0}" = "1" ]; then
  python -m scripts.chart_benchmarks --csv "$CSV" --out "$HTML" --open
else
  python -m scripts.chart_benchmarks --csv "$CSV" --out "$HTML"
fi

echo "✓ Done. Open $HTML"
