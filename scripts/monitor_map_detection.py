#!/usr/bin/env python3
"""Terminal dashboard for the resumable map-detection runner."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "data" / "ai_map_detection"
PREFERRED_STATE = OUTPUT_DIR / "map_detection_prefilter_latest_state.json"
FALLBACK_STATE = OUTPUT_DIR / "map_detection_latest_first_state.json"


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return {}, f"missing: {relative(path)}"
    except json.JSONDecodeError as exc:
        return {}, f"invalid json: {relative(path)}:{exc.lineno}:{exc.colno}"
    except OSError as exc:
        return {}, f"read failed: {relative(path)}: {exc}"
    if not isinstance(value, dict):
        return {}, f"not an object: {relative(path)}"
    return value, None


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def human_age(value: Any) -> str:
    seconds = age_seconds(value)
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "-"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours}h {minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours:02d}h"


def format_eta(seconds: float | int | None) -> str:
    if seconds is None:
        return "-"
    finish = dt.datetime.now().astimezone() + dt.timedelta(seconds=max(0, int(seconds)))
    return f"{format_duration(seconds)} (~{finish:%H:%M})"


def age_seconds(value: Any) -> int | None:
    parsed = parse_ts(value)
    if parsed is None:
        return None
    return max(0, int((utc_now() - parsed).total_seconds()))


def colorize(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{color}{text}{RESET}"


def visible_len(text: str) -> int:
    return len(ANSI_RE.sub("", text))


def pad_visible(text: str, width: int) -> str:
    return text + (" " * max(0, width - visible_len(text)))


def truncate(text: Any, width: int) -> str:
    value = str(text)
    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def truncate_visible(text: Any, width: int) -> str:
    value = ANSI_RE.sub("", str(text))
    return truncate(value, width)


def fit_visible(text: Any, width: int) -> str:
    value = str(text)
    if visible_len(value) <= width:
        return value
    return truncate_visible(value, width)


def progress_bar(done: int, total: int, width: int, color: bool = True) -> str:
    width = max(8, width)
    if total <= 0:
        return "[" + ("-" * width) + "] --.-%"
    done = max(0, min(done, total))
    filled = int(round(width * (done / total)))
    bar = "#" * filled + "-" * (width - filled)
    percent = 100.0 * done / total
    if done == total:
        bar = colorize(bar, GREEN, color)
    elif done > 0:
        bar = colorize(bar, CYAN, color)
    return f"[{bar}] {percent:5.1f}%"


def visual_bar(done: int, total: int, width: int, color: bool = True, ascii_mode: bool = False) -> str:
    width = max(10, width)
    if total <= 0:
        raw = ("-" if ascii_mode else "░") * width
        return f"{raw} --.-%"
    done = max(0, min(done, total))
    filled = int(round(width * (done / total)))
    full = "#" if ascii_mode else "█"
    empty = "-" if ascii_mode else "░"
    raw = (full * filled) + (empty * (width - filled))
    pct = 100.0 * done / total
    bar_color = GREEN if done >= total else CYAN
    return f"{colorize(raw, bar_color, color)} {pct:5.1f}%"


def glyphs(ascii_mode: bool) -> dict[str, str]:
    if ascii_mode:
        return {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|"}
    return {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│"}


def panel(title: str, body: list[str], width: int, color: bool = True, ascii_mode: bool = False) -> list[str]:
    marks = glyphs(ascii_mode)
    width = max(44, width)
    inner = width - 4
    title_text = f" {title} "
    top_fill = max(0, width - visible_len(title_text) - 2)
    top = marks["tl"] + title_text + (marks["h"] * top_fill) + marks["tr"]
    bottom = marks["bl"] + (marks["h"] * (width - 2)) + marks["br"]
    rows = [colorize(top, DIM, color)]
    for line in body:
        clean = fit_visible(line, inner)
        rows.append(colorize(marks["v"], DIM, color) + " " + pad_visible(clean, inner) + " " + colorize(marks["v"], DIM, color))
    rows.append(colorize(bottom, DIM, color))
    return rows


def status_pill(label: str, color_name: str, color: bool) -> str:
    return colorize(f" {label.upper()} ", BOLD + color_name, color)


def tail_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not path.exists():
        return []
    rows: collections.deque[dict[str, Any]] = collections.deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return list(rows)


def run_command(command: list[str], timeout: float = 2.0) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def first_temp(line: str) -> float | None:
    match = re.search(r"\+([0-9]+(?:\.[0-9]+)?)", line)
    if not match:
        return None
    return float(match.group(1))


def parse_sensors_output(output: str) -> dict[str, float]:
    values: dict[str, float] = {}
    acpi_values: list[float] = []
    core_values: list[float] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        temp = first_temp(line)
        if temp is None:
            continue
        if line.startswith("Package id"):
            values["cpu_package_c"] = temp
        elif re.match(r"Core \d+:", line):
            core_values.append(temp)
        elif line.startswith("Composite:"):
            values["nvme_c"] = temp
        elif line.startswith("temp"):
            acpi_values.append(temp)
    if core_values:
        values["cpu_core_max_c"] = max(core_values)
    if acpi_values:
        values["acpi_max_c"] = max(acpi_values)
    return values


def read_temperatures() -> dict[str, Any]:
    sensors = parse_sensors_output(run_command(["sensors"]))
    gpu = read_gpu_stats()
    return {"sensors": sensors, "gpu": gpu}


def read_gpu_stats() -> dict[str, Any]:
    output = run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,temperature.gpu,power.draw,power.limit,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    first = next((line for line in output.splitlines() if line.strip()), "")
    if not first:
        return {}
    parts = [part.strip() for part in first.split(",")]
    if len(parts) < 7:
        return {}
    return {
        "name": parts[0],
        "temp_c": parse_float(parts[1]),
        "power_w": parse_float(parts[2]),
        "power_limit_w": parse_float(parts[3]),
        "util_pct": parse_float(parts[4]),
        "memory_used_mib": parse_float(parts[5]),
        "memory_total_mib": parse_float(parts[6]),
    }


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def read_memory() -> dict[str, float]:
    values: dict[str, int] = {}
    try:
        with Path("/proc/meminfo").open("r", encoding="utf-8") as handle:
            for line in handle:
                key, raw = line.split(":", 1)
                match = re.search(r"\d+", raw)
                if match:
                    values[key] = int(match.group(0))
    except OSError:
        return {}
    total = values.get("MemTotal")
    avail = values.get("MemAvailable")
    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
    result: dict[str, float] = {}
    if total and avail is not None:
        result["mem_total_gib"] = total / 1024 / 1024
        result["mem_avail_gib"] = avail / 1024 / 1024
        result["mem_used_pct"] = 100.0 * (total - avail) / total
    if swap_total and swap_free is not None:
        result["swap_total_gib"] = swap_total / 1024 / 1024
        result["swap_free_gib"] = swap_free / 1024 / 1024
    return result


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        pass
    else:
        return True
    if run_command(["ps", "-p", str(pid), "-o", "pid="]).strip():
        return True
    if shutil.which("rtk") and run_command(["rtk", "ps", "-p", str(pid), "-o", "pid="]).strip():
        return True
    return False


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def count_statuses(state: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in (state.get("issues") or {}).values():
        if not isinstance(status, dict):
            continue
        name = str(status.get("status") or "unknown")
        counts[name] = counts.get(name, 0) + 1
    return counts


def current_issue_key(state: dict[str, Any]) -> str | None:
    running = [
        (key, value)
        for key, value in (state.get("issues") or {}).items()
        if isinstance(value, dict) and value.get("status") == "running"
    ]
    if running:
        running.sort(key=lambda item: str(item[1].get("updated_at") or ""))
        return str(running[-1][0])
    return None


def issue_slug(key: str, suffix: str) -> str:
    year, issue = key.split("/", 1)
    clean_suffix = suffix.strip("_")
    return f"{year}_{issue}_{clean_suffix}" if clean_suffix else f"{year}_{issue}"


def resolve_state_path(value: Path | None) -> Path:
    if value:
        return value
    if PREFERRED_STATE.exists():
        return PREFERRED_STATE
    return FALLBACK_STATE


def default_events_path(state: dict[str, Any], args: argparse.Namespace) -> Path:
    if args.events:
        return args.events
    suffix = args.output_suffix or str(state.get("output_suffix") or "hybrid_prefilter_latest")
    return OUTPUT_DIR / f"map_detection_{suffix}_events.jsonl"


def default_pid_path(state: dict[str, Any], args: argparse.Namespace) -> Path:
    if args.pid_file:
        return args.pid_file
    suffix = args.output_suffix or str(state.get("output_suffix") or "hybrid_prefilter_latest")
    return OUTPUT_DIR / f"map_detection_{suffix}.pid"


def default_issue_status_path(state: dict[str, Any], args: argparse.Namespace) -> Path | None:
    key = current_issue_key(state)
    if not key:
        return None
    suffix = args.output_suffix or str(state.get("output_suffix") or "hybrid_prefilter_latest")
    return OUTPUT_DIR / f"map_issue_status_{issue_slug(key, suffix)}.json"


def latest_event(events: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("event") == name:
            return event
    return None


def events_since_last_runner_start(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last_index = 0
    for index, event in enumerate(events):
        if event.get("event") == "runner_start":
            last_index = index
    return events[last_index:]


def issue_runtime_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    scoped = events_since_last_runner_start(events)
    starts: dict[str, dt.datetime] = {}
    durations: list[float] = []
    finished = 0
    skipped = 0
    latest_start: dict[str, Any] | None = None
    for event in scoped:
        name = event.get("event")
        issue = str(event.get("issue") or "")
        if name == "issue_start":
            latest_start = event
        if name == "issue_skip_completed":
            skipped += 1
        if name == "issue_process_start" and issue:
            ts = parse_ts(event.get("ts"))
            if ts is not None:
                starts[issue] = ts
        if name == "issue_process_end" and issue:
            end = parse_ts(event.get("ts"))
            start = starts.get(issue)
            if start is not None and end is not None and end >= start:
                durations.append((end - start).total_seconds())
                finished += 1
    recent = durations[-12:]
    avg_seconds = (sum(recent) / len(recent)) if recent else None
    return {
        "avg_issue_seconds": avg_seconds,
        "finished_this_run": finished,
        "skipped_this_run": skipped,
        "latest_issue_start": latest_start,
        "sample_count": len(recent),
    }


def issue_page_eta(issue: dict[str, Any], issue_status: dict[str, Any]) -> float | None:
    page_index = int(issue_status.get("page_index") or 0)
    page_total = int(issue_status.get("selected_page_count") or 0)
    if page_index <= 0 or page_total <= 0 or page_index >= page_total:
        return None
    started = parse_ts(issue.get("started_at"))
    if started is None:
        return None
    elapsed = (utc_now() - started).total_seconds()
    if elapsed <= 0:
        return None
    per_page = elapsed / page_index
    return per_page * (page_total - page_index)


def overall_eta(
    remaining_issues: int,
    current_issue_eta: float | None,
    avg_issue_seconds: float | None,
    cooldown_seconds: float,
) -> float | None:
    if avg_issue_seconds is None:
        return None
    if remaining_issues <= 0:
        return 0
    per_issue = avg_issue_seconds + max(0.0, cooldown_seconds)
    if current_issue_eta is None:
        return remaining_issues * per_issue
    return current_issue_eta + max(0, remaining_issues - 1) * per_issue


def render_dashboard(args: argparse.Namespace) -> str:
    state_path = resolve_state_path(args.state)
    state, state_error = read_json(state_path)
    events_path = default_events_path(state, args)
    pid_path = default_pid_path(state, args)
    issue_status_path = default_issue_status_path(state, args)
    issue_status, issue_status_error = ({}, None)
    if issue_status_path:
        issue_status, issue_status_error = read_json(issue_status_path)
    events = tail_jsonl(events_path, args.events_limit)
    temps = read_temperatures()
    memory = read_memory()
    pid = read_pid(pid_path)
    counts = count_statuses(state)
    running_key = current_issue_key(state)
    total = int(state.get("total_issue_count") or max(1, sum(counts.values())))
    done = counts.get("completed", 0) + counts.get("skipped_completed", 0)
    failed = counts.get("failed", 0)
    interrupted = counts.get("interrupted", 0)
    remaining = max(0, total - done - failed)
    pending = max(0, total - sum(counts.values()))
    run_stats = issue_runtime_stats(events)
    current_issue = (state.get("issues") or {}).get(running_key or "") or {}
    current_issue_eta = issue_page_eta(current_issue, issue_status) if running_key else None
    cooldown_seconds = float(state.get("sleep_between_issues") or 0)
    eta_seconds = overall_eta(
        remaining,
        current_issue_eta,
        run_stats.get("avg_issue_seconds"),
        cooldown_seconds,
    )
    width = shutil.get_terminal_size((100, 30)).columns
    width = max(78, min(120, width))
    bar_width = max(18, min(44, width - 52))
    color = not args.no_color
    ascii_mode = args.ascii

    lines = []
    runner_state = str(state.get("status") or "unknown")
    recent_state = age_seconds(state.get("updated_at"))
    alive_text = "alive" if pid_alive(pid) else "not seen"
    if pid is None:
        alive_text = "pid missing"
    elif runner_state == "running" and recent_state is not None and recent_state < max(90, int(args.interval * 4)):
        alive_text = "state updating"
    state_color = GREEN if runner_state == "running" and failed == 0 else YELLOW
    if failed:
        state_color = RED
    run_elapsed = age_seconds(state.get("resumed_at"))
    avg_issue = run_stats.get("avg_issue_seconds")
    title = "SSS MAP DETECTION"
    mode_label = "SAFE MODE" if state.get("safe_mode") else "NORMAL MODE"
    subtitle_left = (
        f"{status_pill(runner_state, state_color, color)} "
        f"PID {pid or '-'} {alive_text}   "
        f"{mode_label}   DPI {state.get('dpi', '-')}"
    )
    subtitle_right = (
        f"elapsed {format_duration(run_elapsed)}   "
        f"ETA est. {format_eta(eta_seconds)}   "
        f"done {done}/{total}   left {remaining}"
    )
    title_line = title + " " + ("-" * max(1, width - len(title) - 1))
    lines.append(colorize(title_line, BOLD + CYAN, color))
    lines.append(truncate_visible(subtitle_left, width))
    lines.append(truncate_visible(subtitle_right, width))
    lines.append("")
    lines.extend(
        panel(
            "RUN",
            [
                f"ISSUES  {visual_bar(done, total, bar_width, color, ascii_mode)}   {done}/{total} done   {remaining} left",
                f"RATE    recent finished {run_stats['finished_this_run']}   avg {format_duration(avg_issue)}   sample {run_stats['sample_count']}",
                f"HEALTH  failures {failed}   interrupted {interrupted}   pending~ {pending}   state age {human_age(state.get('updated_at'))}",
            ],
            width,
            color,
            ascii_mode,
        )
    )
    if state_error:
        lines.extend(panel("WARNINGS", [colorize(f"state warning: {state_error}", RED, color)], width, color, ascii_mode))
    lines.append("")

    lines.extend(
        render_current_issue(
            state,
            issue_status,
            issue_status_error,
            running_key,
            run_stats.get("latest_issue_start"),
            current_issue_eta,
            bar_width,
            width,
            color,
            ascii_mode,
        )
    )
    lines.append("")
    lines.extend(render_system_panel(temps, memory, width, color, ascii_mode))
    lines.append("")
    lines.extend(render_recent_events(events, width, color, ascii_mode))
    footer = f"state={relative(state_path)}  events={relative(events_path)}"
    if args.once:
        footer += "  once=true"
    else:
        footer += f"  refresh={args.interval:.1f}s  quit=Ctrl-C"
    lines.append("")
    lines.append(colorize(truncate(footer, width), DIM, color))
    return "\n".join(lines)


def render_current_issue(
    state: dict[str, Any],
    issue_status: dict[str, Any],
    issue_status_error: str | None,
    running_key: str | None,
    latest_issue_start: dict[str, Any] | None,
    current_issue_eta: float | None,
    bar_width: int,
    terminal_width: int,
    color: bool,
    ascii_mode: bool,
) -> list[str]:
    if not running_key:
        return panel(
            "CURRENT PDF",
            ["idle: scanning completed cache / waiting for next issue"],
            terminal_width,
            color,
            ascii_mode,
        )
    issue = (state.get("issues") or {}).get(running_key) or {}
    phase = issue_status.get("phase") or issue.get("status") or "running"
    updated = issue_status.get("updated_at") or issue.get("updated_at")
    page = issue_status.get("page")
    page_index = int(issue_status.get("page_index") or 0)
    page_total = int(issue_status.get("selected_page_count") or 0)
    processed_pages = int(issue_status.get("processed_page_count") or page_index or 0)
    remaining_pages = max(0, page_total - processed_pages) if page_total else 0
    candidate = issue_status.get("candidate")
    sources = ",".join(issue_status.get("candidate_sources") or [])
    issue_index = latest_issue_start.get("index") if latest_issue_start else None
    issue_total = latest_issue_start.get("total") if latest_issue_start else state.get("total_issue_count")
    issue_elapsed = age_seconds(issue.get("started_at"))
    pdf_url = issue.get("pdf_url") or "-"
    pdf_path = issue_status.get("pdf_path")
    body = [
        f"{running_key}   issue #{issue_index or '-'}/{issue_total or '-'}   phase {phase}   articles {issue.get('article_count', '-')}",
        f"time     elapsed {format_duration(issue_elapsed)}   ETA {format_eta(current_issue_eta)}   status age {human_age(updated)}",
    ]
    if pdf_path:
        body.append(f"cache    {pdf_path}")
    body.append(f"url      {pdf_url}")
    if issue.get("prefilter"):
        body.append(f"output   {issue.get('prefilter')}")
    if page_total:
        body.append(
            f"PAGES    {visual_bar(page_index, page_total, bar_width, color, ascii_mode)}   "
            f"{processed_pages}/{page_total} done   {remaining_pages} left   page {page or '-'}"
        )
    elif page:
        body.append(f"page     {page}")
    if candidate is not None:
        body.append(f"last     candidate {candidate}   sources {sources or '-'}")
    if issue_status_error:
        body.append(colorize(f"warning  {issue_status_error}", YELLOW, color))
    return panel("CURRENT PDF", body, terminal_width, color, ascii_mode)


def render_system_panel(
    temps: dict[str, Any],
    memory: dict[str, float],
    width: int,
    color: bool,
    ascii_mode: bool,
) -> list[str]:
    sensors = temps.get("sensors") or {}
    gpu = temps.get("gpu") or {}
    temp_parts = []
    if "cpu_package_c" in sensors:
        temp_parts.append(format_temp("CPU pkg", sensors["cpu_package_c"], 80.0, color))
    if "cpu_core_max_c" in sensors:
        temp_parts.append(format_temp("CPU core max", sensors["cpu_core_max_c"], 80.0, color))
    if "nvme_c" in sensors:
        temp_parts.append(format_temp("NVMe", sensors["nvme_c"], 75.0, color))
    if "acpi_max_c" in sensors:
        temp_parts.append(format_temp("ACPI", sensors["acpi_max_c"], 75.0, color))
    if gpu:
        gpu_temp = gpu.get("temp_c")
        if gpu_temp is not None:
            temp_parts.append(format_temp("GPU", float(gpu_temp), 83.0, color))
    body = ["temps   " + ("   ".join(temp_parts) if temp_parts else "unavailable")]
    load = os.getloadavg() if hasattr(os, "getloadavg") else None
    mem_text = "memory: unavailable"
    if memory:
        mem_text = (
            f"memory: avail={memory.get('mem_avail_gib', 0):.1f}GiB/"
            f"{memory.get('mem_total_gib', 0):.1f}GiB used={memory.get('mem_used_pct', 0):.0f}%"
        )
        if memory.get("swap_total_gib"):
            mem_text += f" swap_free={memory.get('swap_free_gib', 0):.1f}GiB"
    load_text = f"load: {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}" if load else "load: -"
    body.append(f"{mem_text}   {load_text}")
    if gpu:
        gpu_mem = ""
        if gpu.get("memory_total_mib"):
            gpu_mem = f" mem={gpu.get('memory_used_mib', 0):.0f}/{gpu.get('memory_total_mib', 0):.0f}MiB"
        power = ""
        if gpu.get("power_w") is not None:
            power = f" power={gpu.get('power_w'):.1f}/{gpu.get('power_limit_w'):.0f}W"
        util = ""
        if gpu.get("util_pct") is not None:
            util = f" util={gpu.get('util_pct'):.0f}%"
        body.append(f"gpu     {truncate(gpu.get('name') or '-', 28)}{util}{gpu_mem}{power}")
    return panel("SYSTEM", body, width, color, ascii_mode)


def format_temp(label: str, value: float, warn_at: float, color: bool) -> str:
    text = f"{label}={value:.0f}C"
    if value >= warn_at:
        return colorize(text, RED, color)
    if value >= warn_at - 10:
        return colorize(text, YELLOW, color)
    return colorize(text, GREEN, color)


def render_recent_events(events: list[dict[str, Any]], width: int, color: bool, ascii_mode: bool) -> list[str]:
    if not events:
        return panel("EVENTS", ["no events"], width, color, ascii_mode)
    rows = []
    for event in events[-8:]:
        name = str(event.get("event") or "-")
        issue = str(event.get("issue") or event.get("completed_issue") or "-")
        ts = str(event.get("ts") or "-").replace("+00:00", "Z")
        detail = ""
        if event.get("exit_code") is not None:
            detail = f" exit={event.get('exit_code')}"
        elif event.get("seconds") is not None:
            detail = f" sleep={event.get('seconds')}s"
        elif event.get("failure_count") is not None:
            detail = f" failures={event.get('failure_count')}"
        color_name = GREEN
        if "failed" in name or event.get("exit_code") not in (None, 0):
            color_name = RED
        elif "start" in name or "sleep" in name:
            color_name = CYAN
        row = f"{ts[-9:]}  {name:<20} {issue}{detail}"
        rows.append(colorize(row, color_name, color))
    return panel("EVENTS", rows, width, color, ascii_mode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, help="Runner state JSON. Defaults to the active prefilter state if present.")
    parser.add_argument("--events", type=Path, help="Runner event JSONL. Defaults from state output_suffix.")
    parser.add_argument("--pid-file", type=Path, help="Runner PID file. Defaults from state output_suffix.")
    parser.add_argument("--output-suffix", help="Override suffix used for default event/pid/status paths.")
    parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds.")
    parser.add_argument("--events-limit", type=int, default=80)
    parser.add_argument("--once", action="store_true", help="Render one dashboard frame and exit.")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear the terminal before rendering.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII borders and bars instead of Unicode visuals.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.once:
        print(render_dashboard(args))
        return 0

    hide_cursor = "\033[?25l"
    show_cursor = "\033[?25h"
    try:
        if not args.no_color:
            sys.stdout.write(hide_cursor)
        while True:
            if not args.no_clear:
                sys.stdout.write("\033[2J\033[H")
            print(render_dashboard(args), flush=True)
            time.sleep(max(0.5, args.interval))
    except KeyboardInterrupt:
        return 0
    finally:
        if not args.no_color:
            sys.stdout.write(show_cursor + RESET)
            sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
