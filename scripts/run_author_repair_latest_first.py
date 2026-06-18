#!/usr/bin/env python3
"""Run anonymous-author tail-signature repair from newest issues to oldest."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import repair_anonymous_tail_signatures as repair


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = BASE_DIR / "data" / "author_signature_repairs" / "batch_latest_first"
DEFAULT_STATE_PATH = BASE_DIR / "data" / "author_signature_repairs" / "author_repair_latest_first_state.json"
DEFAULT_EVENTS_PATH = BASE_DIR / "data" / "author_signature_repairs" / "author_repair_latest_first_events.jsonl"
DEFAULT_PID_PATH = BASE_DIR / "data" / "author_signature_repairs" / "author_repair_latest_first.pid"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def append_event(path: Path, event: str, **fields: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": utc_now(), "event": event, **fields}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def issue_sort_key(issue: str) -> tuple[int, int | str]:
    text = str(issue or "")
    try:
        return (1, int(text))
    except ValueError:
        return (0, text)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(value)).strip("._")
    return slug or "issue"


def issue_label(year: int, issue: str) -> str:
    return f"{year}/{issue}"


def has_anonymous(article: dict[str, Any]) -> bool:
    return repair.has_anonymous_author(article)


def count_anonymous(articles: list[dict[str, Any]], year: int | None = None, issue: str | None = None) -> int:
    total = 0
    for article in articles:
        if year is not None and article.get("year") != year:
            continue
        if issue is not None and str(article.get("issue") or "") != str(issue):
            continue
        if has_anonymous(article):
            total += 1
    return total


def anonymous_issue_groups(articles: list[dict[str, Any]]) -> list[tuple[int, str]]:
    groups: set[tuple[int, str]] = set()
    for article in articles:
        if not has_anonymous(article):
            continue
        try:
            year = int(article.get("year") or 0)
        except (TypeError, ValueError):
            continue
        issue = str(article.get("issue") or "")
        if not year or not issue:
            continue
        groups.add((year, issue))
    return sorted(groups, key=lambda item: (item[0], issue_sort_key(item[1])), reverse=True)


def base_state(args: argparse.Namespace, issues: list[tuple[int, str]], anonymous_start: int) -> dict[str, Any]:
    return {
        "status": "running",
        "pid": os.getpid(),
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "apply": bool(args.apply),
        "min_confidence": args.min_confidence,
        "gemma_fallback": bool(args.gemma_fallback),
        "gemma_model": args.gemma_model,
        "issues_total": len(issues),
        "issues_done": 0,
        "anonymous_start": anonymous_start,
        "anonymous_current": anonymous_start,
        "current": None,
        "totals": {
            "scanned": 0,
            "changed": 0,
            "review": 0,
            "skipped": 0,
            "applied": 0,
            "frontend_applied": 0,
            "recommended_apply_count": 0,
            "gemma_calls": 0,
        },
        "last_report": None,
        "errors": [],
    }


def write_state(state_path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    atomic_write_json(state_path, state)


def repair_one_issue(
    articles: list[dict[str, Any]],
    args: argparse.Namespace,
    year: int,
    issue: str,
    report_dir: Path,
) -> dict[str, Any]:
    report = repair.repair_candidates(
        articles,
        year=year,
        issue=issue,
        all_issues=False,
        article_ids=None,
        limit=None,
        use_gemma=args.use_gemma,
        gemma_fallback=args.gemma_fallback,
        gemma_model=args.gemma_model,
        gemma_limit=max(0, args.gemma_limit_per_issue),
        gemma_timeout=args.gemma_timeout,
        ollama_url=args.ollama_url,
    )

    applied = 0
    frontend_applied = 0
    if args.apply:
        latest_articles = repair.read_articles(Path(args.articles))
        applied = repair.apply_changes(latest_articles, report["changes"], args.min_confidence)
        articles[:] = latest_articles
        if applied:
            repair.write_articles(Path(args.articles), articles)
            frontend_applied = repair.sync_frontend(Path(args.frontend), report["changes"], args.min_confidence)

    report["applied"] = applied
    report["frontend_applied"] = frontend_applied
    report["mode"] = "apply" if args.apply else "dry_run"
    report["filters"] = {"year": year, "issue": issue}
    report["recommended_apply_count"] = sum(
        1 for change in report["changes"] if float(change.get("confidence") or 0) >= args.min_confidence
    )

    report_path = report_dir / f"anonymous_tail_signatures_{safe_slug(str(year) + '_' + issue)}_{report['mode']}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report"] = str(report_path)
    return report


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch repair anonymous authors from newest issue to oldest.")
    parser.add_argument("--articles", default=str(repair.ARTICLES_PATH), help="Canonical articles JSON.")
    parser.add_argument("--frontend", default=str(repair.FRONTEND_ARTICLES_PATH), help="Frontend articles JSON to sync on --apply.")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Per-issue report directory.")
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH), help="Progress state JSON path.")
    parser.add_argument("--events", default=str(DEFAULT_EVENTS_PATH), help="Progress events JSONL path.")
    parser.add_argument("--pid-file", default=str(DEFAULT_PID_PATH), help="PID file path.")
    parser.add_argument("--apply", action="store_true", help="Write high-confidence repairs.")
    parser.add_argument("--min-confidence", type=float, default=0.88)
    parser.add_argument("--sleep-seconds", type=positive_float, default=1.5, help="Pause between issues to reduce system load.")
    parser.add_argument("--limit-issues", type=positive_int, help="Process only the newest N issue groups.")
    parser.add_argument("--use-gemma", action="store_true", help="Ask Gemma to confirm deterministic candidates.")
    parser.add_argument("--gemma-fallback", action="store_true", help="Ask Gemma to extract missing tail signatures.")
    parser.add_argument("--gemma-model", default="gemma4:e2b-it-qat")
    parser.add_argument("--gemma-limit-per-issue", type=int, default=0)
    parser.add_argument("--gemma-timeout", type=int, default=120)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    articles_path = Path(args.articles)
    state_path = Path(args.state)
    events_path = Path(args.events)
    pid_path = Path(args.pid_file)
    report_dir = Path(args.report_dir)

    articles = repair.read_articles(articles_path)
    issues = anonymous_issue_groups(articles)
    if args.limit_issues is not None:
        issues = issues[: args.limit_issues]

    anonymous_start = count_anonymous(articles)
    state = base_state(args, issues, anonymous_start)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    write_state(state_path, state)
    append_event(events_path, "batch_start", pid=os.getpid(), issues_total=len(issues), anonymous_start=anonymous_start)

    completed = False
    try:
        for index, (year, issue) in enumerate(issues, start=1):
            articles[:] = repair.read_articles(articles_path)
            label = issue_label(year, issue)
            before_issue = count_anonymous(articles, year, issue)
            state["current"] = {
                "index": index,
                "issue": label,
                "year": year,
                "issue_value": issue,
                "anonymous_before": before_issue,
                "started_at": utc_now(),
                "phase": "repair_issue",
            }
            write_state(state_path, state)
            append_event(events_path, "issue_start", issue=label, anonymous_before=before_issue, index=index)

            try:
                report = repair_one_issue(articles, args, year, issue, report_dir)
            except Exception as exc:
                state["errors"].append({"issue": label, "error": str(exc), "ts": utc_now()})
                append_event(events_path, "issue_error", issue=label, error=str(exc))
                write_state(state_path, state)
                if args.sleep_seconds:
                    time.sleep(args.sleep_seconds)
                continue

            after_issue = count_anonymous(articles, year, issue)
            state["issues_done"] = index
            state["anonymous_current"] = count_anonymous(articles)
            state["last_report"] = report.get("report")
            state["current"] = {
                "index": index,
                "issue": label,
                "year": year,
                "issue_value": issue,
                "anonymous_before": before_issue,
                "anonymous_after": after_issue,
                "phase": "issue_done",
                "report": report.get("report"),
            }
            for key in state["totals"]:
                state["totals"][key] += int(report.get(key) or 0)
            write_state(state_path, state)
            append_event(
                events_path,
                "issue_finish",
                issue=label,
                scanned=report.get("scanned"),
                changed=report.get("changed"),
                applied=report.get("applied"),
                review=report.get("review"),
                skipped=report.get("skipped"),
                anonymous_after=after_issue,
                report=report.get("report"),
            )
            if args.sleep_seconds and index < len(issues):
                append_event(events_path, "cooldown_sleep", issue=label, sleep=args.sleep_seconds)
                time.sleep(args.sleep_seconds)

        state["status"] = "complete"
        state["finished_at"] = utc_now()
        state["current"] = None
        write_state(state_path, state)
        append_event(events_path, "batch_finish", anonymous_current=state["anonymous_current"], issues_done=state["issues_done"])
        completed = True
        return 0
    except KeyboardInterrupt:
        state["status"] = "interrupted"
        state["interrupted_at"] = utc_now()
        write_state(state_path, state)
        append_event(events_path, "batch_interrupted", issues_done=state["issues_done"])
        raise
    finally:
        if completed and pid_path.exists():
            pid_path.unlink()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
