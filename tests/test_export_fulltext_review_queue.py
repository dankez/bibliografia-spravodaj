import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_fulltext_review_queue as exporter


def test_build_queue_exports_only_active_non_ignored_incidents():
    audit = {
        "summary": {
            "generated_at": "2026-06-30T00:00:00+00:00",
            "ignored_outer_matter_records": 1,
            "records_without_text": 2,
            "duplicate_article_ids": 0,
        },
        "records": [
            {
                "id": 1,
                "line": 10,
                "title": "Chybný článok",
                "year": 2000,
                "status": "empty_text",
                "text_chars": 0,
                "words": 0,
                "issue_score": 300,
                "issues": [{"code": "empty_text", "severity": "high", "detail": "missing"}],
                "pdf_url": "https://example.test/a.pdf",
                "pdf_page_start": 5,
                "pdf_page_links": [{"page": 4, "url": "https://example.test/a.pdf#page=4"}],
            },
            {
                "id": 2,
                "line": 11,
                "title": "Obálka",
                "year": 2000,
                "ignored_reason": "outer_matter_page",
                "issue_score": 0,
                "issues": [],
            },
            {
                "id": 3,
                "line": 12,
                "title": "OK",
                "year": 2000,
                "issue_score": 0,
                "issues": [],
            },
            {
                "id": 4,
                "line": 13,
                "title": "Len layout",
                "year": 2001,
                "status": "ok",
                "text_chars": 1000,
                "words": 120,
                "issue_score": 30,
                "issues": [{"code": "cleanup_multispace_layout", "severity": "low", "detail": "layout"}],
            },
            {
                "id": 5,
                "line": 14,
                "title": "Diakritika aj layout",
                "year": 2002,
                "status": "ok",
                "text_chars": 1000,
                "words": 120,
                "issue_score": 130,
                "issues": [
                    {"code": "residual_bad_diacritic_tokens", "severity": "medium", "detail": "jaskyn"},
                    {"code": "cleanup_multispace_layout", "severity": "low", "detail": "layout"},
                ],
                "pdf_page_links": [{"page": 8, "url": "https://example.test/a.pdf#page=8"}],
            },
        ],
    }

    queue = exporter.build_queue(audit)

    assert queue["summary"]["active_incidents"] == 2
    assert queue["summary"]["high"] == 1
    assert queue["summary"]["first_year"] == 2000
    assert queue["summary"]["last_year"] == 2002
    assert queue["summary"]["ignored_outer_matter"] == 1
    assert queue["summary"]["auto_fixable_records_excluded"] == 1
    assert queue["incidents"][0]["id"] == 1
    assert queue["incidents"][0]["primary_label"] == "Chýba fulltext"
    assert queue["incidents"][0]["pdf_links"] == [{"page": 5, "url": "https://example.test/a.pdf#page=5"}]
    assert queue["incidents"][1]["id"] == 5
    assert queue["incidents"][1]["issue_codes"] == ["residual_bad_diacritic_tokens"]
    assert queue["incidents"][1]["auto_fixable_issue_codes"] == ["cleanup_multispace_layout"]
    assert queue["incidents"][1]["pdf_links"] == [{"page": 8, "url": "https://example.test/a.pdf#page=8"}]


def test_build_summary_omits_incident_payload():
    queue = {
        "generated_at": "2026-06-30T00:00:01+00:00",
        "source_generated_at": "2026-06-30T00:00:00+00:00",
        "summary": {"active_incidents": 2},
        "issue_labels": {"empty_text": "Chýba fulltext"},
        "incidents": [{"id": 1}, {"id": 2}],
    }

    summary = exporter.build_summary(queue)

    assert summary["summary"]["active_incidents"] == 2
    assert summary["issue_labels"]["empty_text"] == "Chýba fulltext"
    assert "incidents" not in summary
