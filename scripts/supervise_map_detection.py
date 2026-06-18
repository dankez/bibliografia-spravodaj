#!/usr/bin/env python3
"""Keep the latest-first map detection runner alive until it finishes."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "data" / "ai_map_detection"
RUNNER = BASE_DIR / "scripts" / "run_map_detection_latest_first.py"
DEFAULT_STATE = OUTPUT_DIR / "map_detection_prefilter_latest_state.json"
DEFAULT_LOG = OUTPUT_DIR / "map_detection_prefilter_latest.out"
DEFAULT_RUNNER_PID = OUTPUT_DIR / "map_detection_prefilter_latest.pid"
DEFAULT_SUPERVISOR_LOG = OUTPUT_DIR / "map_detection_prefilter_latest_supervisor.out"
DEFAULT_SUPERVISOR_PID = OUTPUT_DIR / "map_detection_prefilter_latest_supervisor.pid"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def append_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_now()}] {message}\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def state_completed(path: Path) -> bool:
    try:
        state = read_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    return str(state.get("status") or "").startswith("completed")


def read_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_cmdline(pid: int | None) -> str:
    if pid is None or pid <= 1:
        return ""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def runner_alive(pid_file: Path) -> bool:
    pid = read_pid(pid_file)
    if not pid_alive(pid):
        return False
    return "run_map_detection_latest_first.py" in pid_cmdline(pid)


def build_runner_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(RUNNER),
        "--output-suffix",
        args.output_suffix,
        "--state",
        str(args.state),
    ]
    if args.no_ai:
        command.append("--no-ai")
    if args.year_from is not None:
        command.extend(["--year-from", str(args.year_from)])
    if args.year_to is not None:
        command.extend(["--year-to", str(args.year_to)])
    if args.max_issues is not None:
        command.extend(["--max-issues", str(args.max_issues)])
    return command


def supervise(args: argparse.Namespace) -> int:
    append_line(args.supervisor_log, "SUPERVISOR start")
    command = build_runner_command(args)
    failures = 0

    while True:
        if state_completed(args.state):
            append_line(args.supervisor_log, "SUPERVISOR done: state completed")
            return 0

        if runner_alive(args.runner_pid_file):
            time.sleep(args.interval)
            continue

        failures += 1
        append_line(args.supervisor_log, f"runner not alive; starting attempt={failures}: {' '.join(command)}")
        with args.log_file.open("a", encoding="utf-8") as log:
            log.write(f"\n[{utc_now()}] SUPERVISOR START {' '.join(command)}\n")
            log.flush()
            process = subprocess.Popen(
                command,
                cwd=BASE_DIR,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            args.runner_pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
            code = process.wait()
            log.write(f"[{utc_now()}] SUPERVISOR RUNNER END code={code}\n")
            log.flush()
        append_line(args.supervisor_log, f"runner exited code={code}")
        time.sleep(args.restart_delay)


def detach_self(args: argparse.Namespace) -> int:
    args.supervisor_pid_file.parent.mkdir(parents=True, exist_ok=True)
    child_args = [item for item in sys.argv[1:] if item != "--detach"]
    command = [sys.executable, str(Path(__file__).resolve()), *child_args]
    append_line(args.supervisor_log, f"DETACH {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=BASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    args.supervisor_pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    print(f"supervisor detached pid={process.pid}")
    print(f"supervisor_log={args.supervisor_log}")
    print(f"supervisor_pid_file={args.supervisor_pid_file}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--runner-pid-file", type=Path, default=DEFAULT_RUNNER_PID)
    parser.add_argument("--supervisor-log", type=Path, default=DEFAULT_SUPERVISOR_LOG)
    parser.add_argument("--supervisor-pid-file", type=Path, default=DEFAULT_SUPERVISOR_PID)
    parser.add_argument("--output-suffix", default="hybrid_prefilter_latest")
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument("--max-issues", type=int)
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--restart-delay", type=int, default=15)
    parser.add_argument("--detach", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.state = args.state.resolve()
    args.log_file = args.log_file.resolve()
    args.runner_pid_file = args.runner_pid_file.resolve()
    args.supervisor_log = args.supervisor_log.resolve()
    args.supervisor_pid_file = args.supervisor_pid_file.resolve()
    if args.detach:
        return detach_self(args)
    return supervise(args)


if __name__ == "__main__":
    raise SystemExit(main())
