import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_map_detection_latest_first as runner


def test_empty_summary_is_not_complete(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text("", encoding="utf-8")

    complete, reason = runner.summary_is_complete(summary_path, 2023, "4")

    assert complete is False
    assert reason == "empty"


def test_valid_summary_is_complete(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "year": 2023,
                "issue": "4",
                "processed_page_count": 94,
                "candidate_pages": [41, 43],
                "confirmed_pages": [],
            }
        ),
        encoding="utf-8",
    )

    complete, reason = runner.summary_is_complete(summary_path, 2023, "4")

    assert complete is True
    assert reason is None


def test_summary_for_different_issue_is_not_complete(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "year": 2023,
                "issue": "3",
                "processed_page_count": 10,
                "candidate_pages": [],
                "confirmed_pages": [],
            }
        ),
        encoding="utf-8",
    )

    complete, reason = runner.summary_is_complete(summary_path, 2023, "4")

    assert complete is False
    assert reason == "issue_mismatch"


def test_safe_mode_applies_conservative_defaults():
    class Args:
        safe_mode = True
        no_ai = False
        disable_ocr_objects = False
        dpi = 130
        nice_level = None
        ionice_idle = False
        sleep_between_issues = 0.0

    args = Args()

    runner.apply_safe_mode(args)

    assert args.no_ai is True
    assert args.disable_ocr_objects is True
    assert args.dpi == 100
    assert args.nice_level == 10
    assert args.ionice_idle is True
    assert args.sleep_between_issues == 5.0


def test_mark_stale_running_issues_marks_only_running_issue():
    state = {
        "status": "running",
        "issues": {
            "2017/1": {"status": "running"},
            "2017/2": {"status": "completed"},
        },
    }

    stale = runner.mark_stale_running_issues(state)

    assert stale == ["2017/1"]
    assert state["issues"]["2017/1"]["status"] == "interrupted"
    assert state["issues"]["2017/1"]["interrupt_reason"] == "runner_restarted_after_stale_running_state"
    assert state["issues"]["2017/2"]["status"] == "completed"


def test_load_issues_can_filter_single_issue(tmp_path):
    articles_path = tmp_path / "articles.json"
    articles_path.write_text(
        json.dumps(
            [
                {"year": 2017, "issue": "1", "pdf_url": "https://example.test/1.pdf"},
                {"year": 2017, "issue": "2", "pdf_url": "https://example.test/2.pdf"},
            ]
        ),
        encoding="utf-8",
    )

    class Args:
        articles = articles_path
        year_from = 2017
        year_to = 2017
        issue = "1"
        max_issues = None

    issues = runner.load_issues(Args())

    assert [(item["year"], item["issue"]) for item in issues] == [(2017, "1")]


def test_prefilter_cache_problem_detects_empty_cached_image(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"")
    prefilter = tmp_path / "prefilter.jsonl"
    prefilter.write_text(json.dumps({"page": 7, "image_path": str(image)}) + "\n", encoding="utf-8")

    problem = runner.prefilter_cache_problem(prefilter)

    assert problem == "page_7_empty_image_file"


def test_prefilter_cache_problem_accepts_nonempty_cached_image(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    prefilter = tmp_path / "prefilter.jsonl"
    prefilter.write_text(json.dumps({"page": 7, "image_path": str(image)}) + "\n", encoding="utf-8")

    problem = runner.prefilter_cache_problem(prefilter)

    assert problem is None
