#!/usr/bin/env python3
"""Run resumable hybrid map/plan detection from newest issue backwards."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
OUTPUT_DIR = BASE_DIR / "data" / "ai_map_detection"
STATE_PATH = OUTPUT_DIR / "map_detection_latest_first_state.json"
DETECTOR = BASE_DIR / "scripts" / "hybrid_detect_pdf_maps.py"
MONITOR = BASE_DIR / "scripts" / "monitor_map_detection.py"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)
    fsync_parent(path)


def fsync_parent(path: Path) -> None:
    try:
        fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": utc_now(), **record}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def event_path(args: argparse.Namespace) -> Path:
    return args.events_file or OUTPUT_DIR / f"map_detection_{args.output_suffix}_events.jsonl"


def log_event(args: argparse.Namespace, event: str, **fields: Any) -> None:
    append_jsonl(event_path(args), {"event": event, **fields})


def summary_is_complete(path: Path, year: int, issue: str) -> tuple[bool, str | None]:
    if not path.exists():
        return False, "missing"
    if path.stat().st_size == 0:
        return False, "empty"
    try:
        summary = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid_json: {exc}"
    if not isinstance(summary, dict):
        return False, "not_object"
    if summary.get("year") != year or str(summary.get("issue")) != str(issue):
        return False, "issue_mismatch"
    processed_page_count = summary.get("processed_page_count")
    if not isinstance(processed_page_count, int) or processed_page_count <= 0:
        return False, "missing_processed_pages"
    if not isinstance(summary.get("candidate_pages"), list):
        return False, "missing_candidate_pages"
    if not isinstance(summary.get("confirmed_pages"), list):
        return False, "missing_confirmed_pages"
    return True, None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc
    return records


def resolve_output_path(value: Any) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def prefilter_cache_problem(path: Path) -> str | None:
    if not path.exists():
        return "missing_prefilter"
    if path.stat().st_size == 0:
        return "empty_prefilter"
    try:
        records = load_jsonl(path)
    except RuntimeError as exc:
        return f"invalid_prefilter_jsonl: {exc}"
    if not records:
        return "empty_prefilter"
    for record in records:
        try:
            page = int(record["page"])
        except (KeyError, TypeError, ValueError):
            return "missing_or_invalid_page"
        image_path = str(record.get("image_path") or "").strip()
        if not image_path:
            return f"page_{page}_missing_image_path"
        image = resolve_output_path(image_path)
        if not image.exists():
            return f"page_{page}_missing_image_file"
        if image.stat().st_size == 0:
            return f"page_{page}_empty_image_file"
    return None


def issue_sort_value(issue: str) -> tuple[int, str]:
    try:
        return (int(issue), "")
    except ValueError:
        return (-1, issue)


def issue_slug(year: int, issue: str, suffix: str) -> str:
    clean_suffix = suffix.strip("_")
    return f"{year}_{issue}_{clean_suffix}" if clean_suffix else f"{year}_{issue}"


def summary_path(year: int, issue: str, suffix: str) -> Path:
    return OUTPUT_DIR / f"map_hybrid_{issue_slug(year, issue, suffix)}_summary.json"


def prefilter_path(year: int, issue: str, suffix: str) -> Path:
    return OUTPUT_DIR / f"map_prefilter_{issue_slug(year, issue, suffix)}.jsonl"


def confirmed_path(year: int, issue: str, suffix: str) -> Path:
    return OUTPUT_DIR / f"map_confirmed_{issue_slug(year, issue, suffix)}.jsonl"


def load_issues(args: argparse.Namespace) -> list[dict[str, Any]]:
    articles = read_json(args.articles)
    by_issue: dict[tuple[int, str], dict[str, Any]] = {}
    for article in articles:
        year = article.get("year")
        issue = str(article.get("issue") or "").strip()
        pdf_url = str(article.get("pdf_url") or "").strip()
        if not year or not issue or not pdf_url:
            continue
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            continue
        if args.year_from is not None and year_int < args.year_from:
            continue
        if args.year_to is not None and year_int > args.year_to:
            continue
        if args.issue is not None and issue != str(args.issue).strip():
            continue
        key = (year_int, issue)
        record = by_issue.setdefault(
            key,
            {
                "year": year_int,
                "issue": issue,
                "pdf_url": pdf_url,
                "article_count": 0,
            },
        )
        record["article_count"] += 1
    issues = sorted(
        by_issue.values(),
        key=lambda item: (int(item["year"]), issue_sort_value(str(item["issue"]))),
        reverse=True,
    )
    if args.max_issues:
        issues = issues[: args.max_issues]
    return issues


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "issues": {},
        }
    return read_json(path)


def mark_stale_running_issues(state: dict[str, Any]) -> list[str]:
    stale = []
    if state.get("status") != "running":
        return stale
    for key, status in (state.get("issues") or {}).items():
        if not isinstance(status, dict) or status.get("status") != "running":
            continue
        status["status"] = "interrupted"
        status["interrupted_at"] = utc_now()
        status["interrupt_reason"] = "runner_restarted_after_stale_running_state"
        stale.append(str(key))
    return stale


def issue_key(issue: dict[str, Any]) -> str:
    return f"{issue['year']}/{issue['issue']}"


def run_issue(issue: dict[str, Any], args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(DETECTOR),
        "--year",
        str(issue["year"]),
        "--issue",
        str(issue["issue"]),
        "--output-suffix",
        args.output_suffix,
        "--model",
        args.model,
        "--dpi",
        str(args.dpi),
        "--timeout",
        str(args.timeout),
        "--ocr-languages",
        args.ocr_languages,
        "--ocr-timeout",
        str(args.ocr_timeout),
        "--ignore-first-pages",
        str(args.ignore_first_pages),
        "--ignore-last-pages",
        str(args.ignore_last_pages),
        "--printed-page-offset",
        str(args.printed_page_offset),
        "--progress",
    ]
    if args.no_ai:
        command.append("--no-ai")
    if args.disable_ocr_objects:
        command.append("--disable-ocr-objects")
    if args.reuse_prefilter:
        command.append("--reuse-prefilter")
    if args.force:
        command.append("--force")

    if args.nice_level is not None and shutil.which("nice"):
        command = ["nice", "-n", str(args.nice_level), *command]
    if args.ionice_idle and shutil.which("ionice"):
        command = ["ionice", "-c", "3", *command]

    log_path = OUTPUT_DIR / f"runner_{issue_slug(issue['year'], issue['issue'], args.output_suffix)}.log"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{utc_now()}] START {' '.join(command)}\n")
        log.flush()
        os.fsync(log.fileno())
        log_event(
            args,
            "issue_process_start",
            issue=issue_key(issue),
            command=command,
            log=str(log_path.relative_to(BASE_DIR)),
        )
        process = subprocess.Popen(
            command,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        code = process.wait()
        log.write(f"[{utc_now()}] END code={code}\n")
        log.flush()
        os.fsync(log.fileno())
    log_event(args, "issue_process_end", issue=issue_key(issue), exit_code=code)
    return code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=ARTICLES_PATH)
    parser.add_argument("--state", type=Path, default=STATE_PATH)
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument("--issue", help="Restrict the run to one issue label, e.g. 1, 4, kongres.")
    parser.add_argument("--max-issues", type=int)
    parser.add_argument("--model", default="granite3.2-vision")
    parser.add_argument("--output-suffix", default="hybrid_granite_latest")
    parser.add_argument("--dpi", type=int, default=130)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--ocr-languages", default="slk+ces")
    parser.add_argument("--ocr-timeout", type=int, default=30)
    parser.add_argument("--ignore-first-pages", type=int, default=2)
    parser.add_argument("--ignore-last-pages", type=int, default=4)
    parser.add_argument("--printed-page-offset", type=int, default=2)
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--disable-ocr-objects", action="store_true")
    parser.add_argument("--reuse-prefilter", action="store_true", help="Reuse existing prefilter JSONL and only run confirmation.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--pid-file", type=Path)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--rerun-completed", action="store_true")
    parser.add_argument("--safe-mode", action="store_true", help="Use conservative defaults for unstable overnight runs.")
    parser.add_argument("--nice-level", type=int, help="Run detector child process with this nice level when available.")
    parser.add_argument("--ionice-idle", action="store_true", help="Run detector child process with idle I/O priority when available.")
    parser.add_argument("--sleep-between-issues", type=float, default=0.0)
    parser.add_argument("--events-file", type=Path)
    return parser.parse_args()


def apply_safe_mode(args: argparse.Namespace) -> None:
    if not args.safe_mode:
        return
    args.no_ai = True
    args.disable_ocr_objects = True
    if args.dpi > 100:
        args.dpi = 100
    if args.nice_level is None:
        args.nice_level = 10
    args.ionice_idle = True
    if args.sleep_between_issues <= 0:
        args.sleep_between_issues = 5.0


def detach_self(args: argparse.Namespace) -> int:
    log_path = args.log_file or OUTPUT_DIR / f"map_detection_{args.output_suffix}.out"
    pid_path = args.pid_file or OUTPUT_DIR / f"map_detection_{args.output_suffix}.pid"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    child_args = [item for item in sys.argv[1:] if item != "--detach"]
    command = [sys.executable, str(Path(__file__).resolve()), *child_args]
    log_handle = log_path.open("a", encoding="utf-8")
    log_handle.write(f"\n[{utc_now()}] DETACH {' '.join(command)}\n")
    log_handle.flush()
    process = subprocess.Popen(
        command,
        cwd=BASE_DIR,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    pid_path.write_text(f"{process.pid}\n", encoding="utf-8")
    print(f"detached pid={process.pid}")
    print(f"log={log_path}")
    print(f"pid_file={pid_path}")
    print(f"monitor={sys.executable} {MONITOR} --state {args.state} --output-suffix {args.output_suffix}")
    return 0


def main() -> int:
    args = parse_args()
    apply_safe_mode(args)
    if args.detach:
        return detach_self(args)

    issues = load_issues(args)
    state = load_state(args.state)
    stale_issues = mark_stale_running_issues(state)
    if stale_issues:
        log_event(args, "stale_running_issues_marked", issues=stale_issues)
    state.update(
        {
            "updated_at": utc_now(),
            "status": "running",
            "resumed_at": utc_now(),
            "model": args.model,
            "output_suffix": args.output_suffix,
            "safe_mode": args.safe_mode,
            "dpi": args.dpi,
            "no_ai": args.no_ai,
            "disable_ocr_objects": args.disable_ocr_objects,
            "nice_level": args.nice_level,
            "ionice_idle": args.ionice_idle,
            "sleep_between_issues": args.sleep_between_issues,
            "year_from": args.year_from,
            "year_to": args.year_to,
            "total_issue_count": len(issues),
        }
    )
    state.pop("finished_at", None)
    state.setdefault("issues", {})
    write_json(args.state, state)
    log_event(
        args,
        "runner_start",
        state=str(args.state.relative_to(BASE_DIR) if args.state.is_relative_to(BASE_DIR) else args.state),
        issue_count=len(issues),
        safe_mode=args.safe_mode,
        dpi=args.dpi,
        no_ai=args.no_ai,
        disable_ocr_objects=args.disable_ocr_objects,
    )

    failures = 0
    for index, issue in enumerate(issues, start=1):
        key = issue_key(issue)
        summary = summary_path(issue["year"], issue["issue"], args.output_suffix)
        prefilter = prefilter_path(issue["year"], issue["issue"], args.output_suffix)
        status = state["issues"].get(key, {})
        summary_complete, summary_problem = summary_is_complete(summary, issue["year"], str(issue["issue"]))
        prefilter_problem = prefilter_cache_problem(prefilter) if summary_complete else None
        completed = summary_complete and prefilter_problem is None and not args.rerun_completed
        if summary.exists() and not summary_complete and not args.rerun_completed and not args.force:
            status["previous_summary_error"] = summary_problem
            print(f"[{index}/{len(issues)}] rerun invalid summary {key}: {summary_problem}", flush=True)
        if summary_complete and prefilter_problem and not args.rerun_completed and not args.force:
            status["previous_prefilter_cache_error"] = prefilter_problem
            print(f"[{index}/{len(issues)}] rerun invalid prefilter cache {key}: {prefilter_problem}", flush=True)
        if completed and not args.force:
            status.update(
                {
                    "status": "skipped_completed",
                    "updated_at": utc_now(),
                    "summary": str(summary.relative_to(BASE_DIR)),
                    "prefilter": str(prefilter.relative_to(BASE_DIR)),
                    "confirmed": str(confirmed_path(issue["year"], issue["issue"], args.output_suffix).relative_to(BASE_DIR)),
                }
            )
            state["issues"][key] = status
            state["updated_at"] = utc_now()
            write_json(args.state, state)
            print(f"[{index}/{len(issues)}] skip completed {key}", flush=True)
            log_event(args, "issue_skip_completed", issue=key, index=index, total=len(issues))
            continue

        for field in ("exit_code", "finished_at", "failed_at", "interrupted_at", "interrupt_reason"):
            status.pop(field, None)
        status.update(
            {
                "status": "dry_run" if args.dry_run else "running",
                "started_at": utc_now(),
                "updated_at": utc_now(),
                "year": issue["year"],
                "issue": issue["issue"],
                "article_count": issue["article_count"],
                "pdf_url": issue["pdf_url"],
                "summary": str(summary.relative_to(BASE_DIR)),
                "prefilter": str(prefilter_path(issue["year"], issue["issue"], args.output_suffix).relative_to(BASE_DIR)),
                "confirmed": str(confirmed_path(issue["year"], issue["issue"], args.output_suffix).relative_to(BASE_DIR)),
            }
        )
        state["issues"][key] = status
        state["updated_at"] = utc_now()
        write_json(args.state, state)
        print(f"[{index}/{len(issues)}] start {key} articles={issue['article_count']}", flush=True)
        log_event(args, "issue_start", issue=key, index=index, total=len(issues), article_count=issue["article_count"])

        if args.dry_run:
            continue

        code = run_issue(issue, args)
        status["updated_at"] = utc_now()
        status["exit_code"] = code
        if code == 0:
            status["status"] = "completed"
            status["finished_at"] = utc_now()
        else:
            failures += 1
            status["status"] = "failed"
            status["failed_at"] = utc_now()
        state["issues"][key] = status
        state["updated_at"] = utc_now()
        state["failure_count"] = failures
        write_json(args.state, state)
        log_event(args, "issue_finish", issue=key, exit_code=code, status=status["status"], failure_count=failures)

        if code != 0 and args.stop_on_error:
            return code
        if args.sleep_between_issues > 0 and index < len(issues):
            log_event(args, "cooldown_sleep", seconds=args.sleep_between_issues, completed_issue=key)
            time.sleep(args.sleep_between_issues)

    state["updated_at"] = utc_now()
    state["finished_at"] = utc_now()
    state["status"] = "completed_with_failures" if failures else "completed"
    state["failure_count"] = failures
    write_json(args.state, state)
    log_event(args, "runner_finish", status=state["status"], failure_count=failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
