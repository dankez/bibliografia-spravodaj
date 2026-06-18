import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import monitor_map_detection as monitor


def test_parse_sensors_output_extracts_key_temperatures():
    output = """
coretemp-isa-0000
Package id 0:  +52.0 C  (high = +80.0 C, crit = +100.0 C)
Core 0:        +48.0 C  (high = +80.0 C, crit = +100.0 C)
Core 1:        +55.0 C  (high = +80.0 C, crit = +100.0 C)

nvme-pci-0500
Composite:    +37.9 C  (low  =  -0.1 C, high = +74.8 C)

acpitz-acpi-0
temp1:        +27.8 C
temp2:        +29.8 C
"""

    parsed = monitor.parse_sensors_output(output)

    assert parsed["cpu_package_c"] == 52.0
    assert parsed["cpu_core_max_c"] == 55.0
    assert parsed["nvme_c"] == 37.9
    assert parsed["acpi_max_c"] == 29.8


def test_progress_bar_uses_done_and_total_without_color():
    bar = monitor.progress_bar(5, 10, 10, color=False)

    assert bar == "[#####-----]  50.0%"


def test_current_issue_key_returns_latest_running_issue():
    state = {
        "issues": {
            "2014/1": {"status": "running", "updated_at": "2026-06-18T06:00:00+00:00"},
            "2014/2": {"status": "completed", "updated_at": "2026-06-18T06:01:00+00:00"},
            "2014/3": {"status": "running", "updated_at": "2026-06-18T06:02:00+00:00"},
        }
    }

    assert monitor.current_issue_key(state) == "2014/3"


def test_format_duration_handles_hours():
    assert monitor.format_duration(65) == "1m 05s"
    assert monitor.format_duration(3660) == "1h 01m"


def test_issue_runtime_stats_uses_process_start_end_events():
    events = [
        {"event": "runner_start", "ts": "2026-06-18T06:00:00+00:00"},
        {"event": "issue_process_start", "issue": "2014/1", "ts": "2026-06-18T06:00:10+00:00"},
        {"event": "issue_process_end", "issue": "2014/1", "ts": "2026-06-18T06:00:40+00:00"},
        {"event": "issue_skip_completed", "issue": "2013/4", "ts": "2026-06-18T06:00:41+00:00"},
        {"event": "issue_process_start", "issue": "2013/3", "ts": "2026-06-18T06:01:00+00:00"},
        {"event": "issue_process_end", "issue": "2013/3", "ts": "2026-06-18T06:02:00+00:00"},
    ]

    stats = monitor.issue_runtime_stats(events)

    assert stats["finished_this_run"] == 2
    assert stats["skipped_this_run"] == 1
    assert stats["avg_issue_seconds"] == 45


def test_overall_eta_includes_current_issue_and_remaining_average():
    eta = monitor.overall_eta(
        remaining_issues=3,
        current_issue_eta=20,
        avg_issue_seconds=40,
        cooldown_seconds=5,
    )

    assert eta == 110
