"""Generate docs/stories.json from a Jira CSV export.

The director dashboard reads docs/stories.json for the *planned* story list
(so it can show planned-vs-automated coverage). Rather than hand-maintain it,
export your sprint/board from Jira as CSV and run:

    python -m scripts.import_jira_stories --csv sprint.csv
    python -m scripts.import_jira_stories --csv sprint.csv --issue-types Story,Bug
    python -m scripts.import_jira_stories --csv sprint.csv --out docs/stories.json

Jira column names vary between instances, so headers are auto-detected from the
common variants; override any with --col-* if your export differs. Jira priority
(Highest/High/…) and status (To Do/In Progress/…) are normalized to the schema
the dashboard expects (P1/P2/P3 and backlog/in_progress/in_review/done).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

# Candidate Jira headers (lowercased) for each target field, best match first.
_HEADER_CANDIDATES = {
    "id": ["issue key", "key", "issue id", "id"],
    "title": ["summary", "title"],
    "epic": ["epic name", "epic link", "parent summary", "parent", "epic"],
    "priority": ["priority"],
    "status": ["status"],
    "issue_type": ["issue type", "type"],
}
_TESTTYPE_HEADERS = ["labels", "components", "component/s", "label"]

_PRIORITY_MAP = {
    "highest": "P1", "high": "P1", "blocker": "P1", "critical": "P1", "p1": "P1",
    "medium": "P2", "major": "P2", "p2": "P2",
    "low": "P3", "lowest": "P3", "minor": "P3", "trivial": "P3", "p3": "P3",
}
_STATUS_MAP = {
    "to do": "backlog", "backlog": "backlog", "open": "backlog", "new": "backlog",
    "in progress": "in_progress", "in development": "in_progress", "in dev": "in_progress",
    "in review": "in_review", "code review": "in_review", "review": "in_review",
    "done": "done", "closed": "done", "resolved": "done",
}
_TESTTYPE_TOKENS = ("api", "ui", "email")


def _detect(headers: list[str], candidates: list[str]) -> str | None:
    lower = {h.lower().strip(): h for h in headers}
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def _map_priority(value: str) -> str:
    return _PRIORITY_MAP.get(value.lower().strip(), "") if value else ""


def _map_status(value: str, raw: bool) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if raw:
        return v.lower().replace(" ", "_")
    return _STATUS_MAP.get(v.lower(), v.lower().replace(" ", "_"))


def _infer_type(row: dict, testtype_col: str | None, issue_type: str) -> str:
    """Prefer an api/ui/email token found in labels/components; else the issue type."""
    if testtype_col:
        blob = (row.get(testtype_col) or "").lower()
        for tok in _TESTTYPE_TOKENS:
            if tok in blob:
                return tok
    return issue_type.lower().strip()


def convert(csv_path: Path, *, cols: dict[str, str | None], raw_status: bool,
            issue_types: set[str] | None) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        resolved = {k: cols.get(k) or _detect(headers, cands)
                    for k, cands in _HEADER_CANDIDATES.items()}
        if not resolved["id"] or not resolved["title"]:
            raise SystemExit(
                "Could not find the issue-key/summary columns. Detected headers:\n  "
                + ", ".join(headers) + "\nOverride with --col-id / --col-title.")
        testtype_col = _detect(headers, _TESTTYPE_HEADERS)

        stories: list[dict] = []
        seen: set[str] = set()
        for row in reader:
            sid = (row.get(resolved["id"]) or "").strip()
            title = (row.get(resolved["title"]) or "").strip()
            if not sid or sid in seen:
                continue
            issue_type = (row.get(resolved["issue_type"]) or "").strip() if resolved["issue_type"] else ""
            if issue_types and issue_type.lower() not in issue_types:
                continue
            seen.add(sid)
            stories.append({
                "id": sid,
                "title": title,
                "epic": (row.get(resolved["epic"]) or "").strip() if resolved["epic"] else "",
                "priority": _map_priority(row.get(resolved["priority"], "") if resolved["priority"] else ""),
                "type": _infer_type(row, testtype_col, issue_type),
                "status": _map_status(row.get(resolved["status"], "") if resolved["status"] else "", raw_status),
            })
    return stories


def main() -> None:
    ap = argparse.ArgumentParser(description="Jira CSV export -> docs/stories.json")
    ap.add_argument("--csv", required=True, type=Path, help="Jira CSV export path")
    ap.add_argument("--out", default=Path("docs/stories.json"), type=Path)
    ap.add_argument("--issue-types", help="comma-separated filter, e.g. Story,Bug")
    ap.add_argument("--raw-status", action="store_true",
                    help="keep Jira status text instead of normalizing to backlog/in_progress/...")
    # per-field header overrides
    for f in _HEADER_CANDIDATES:
        ap.add_argument(f"--col-{f.replace('_', '-')}", dest=f"col_{f}", default=None,
                        help=f"exact CSV header for '{f}'")
    args = ap.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"No CSV at {args.csv}")
    cols = {f: getattr(args, f"col_{f}") for f in _HEADER_CANDIDATES}
    types = {t.strip().lower() for t in args.issue_types.split(",")} if args.issue_types else None

    stories = convert(args.csv, cols=cols, raw_status=args.raw_status, issue_types=types)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(stories, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    by_prio = {p: sum(1 for s in stories if s["priority"] == p) for p in ("P1", "P2", "P3")}
    print(f"Wrote {len(stories)} stories -> {args.out}")
    print(f"  by priority: P1={by_prio['P1']} P2={by_prio['P2']} P3={by_prio['P3']} "
          f"(unmapped={sum(1 for s in stories if not s['priority'])})")


if __name__ == "__main__":
    main()
