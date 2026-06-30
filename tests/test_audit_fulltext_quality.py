import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_fulltext_quality as audit


def default_args(**overrides):
    values = {
        "min_chars": 300,
        "min_words": 30,
        "min_chars_per_page": 600,
        "min_words_per_page": 80,
        "bad_token_threshold": 2,
        "hyphen_linebreak_threshold": 100,
        "multispace_threshold": 500,
        "format_char_threshold": 25,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_classify_record_flags_empty_text_as_high_priority():
    record = {"id": 1, "status": "missing_page_range", "text": "", "pages": "1"}

    signals, issues = audit.classify_record(record, default_args())

    assert signals["chars"] == 0
    assert issues[0]["code"] == "empty_text"
    assert issues[0]["severity"] == "high"


def test_classify_record_flags_short_low_density_text():
    record = {
        "id": 2,
        "status": "ok",
        "text": "Prilis kratky text.",
        "pdf_page_start": 10,
        "pdf_page_end": 12,
    }

    _, issues = audit.classify_record(record, default_args())

    assert {issue["code"] for issue in issues} >= {"very_short_text", "low_text_density"}


def test_duplicate_groups_require_normalized_duplicate_text():
    records = [
        {"id": 1, "text": "Rovnaky text " * 60, "title": "A"},
        {"id": 2, "text": ("Rovnaky   text\n" * 60).strip(), "title": "B"},
        {"id": 3, "text": "Ine znenie " * 60, "title": "C"},
    ]

    groups = audit.duplicate_groups(records, min_chars=100)

    assert len(groups) == 1
    assert groups[0]["record_count"] == 2
    assert [item["id"] for item in groups[0]["records"]] == [1, 2]


def test_pdf_page_links_use_article_physical_range():
    record = {
        "pdf_url": "https://example.test/issue.pdf",
        "pdf_page_start": 10,
        "pdf_page_end": 12,
    }

    links = audit.pdf_page_links(record, pdf_pages=40)

    assert [link["page"] for link in links] == [10, 11, 12]
    assert links[0]["url"] == "https://example.test/issue.pdf#page=10"


def test_pdf_page_links_use_pdf_tail_for_out_of_range_record():
    record = {
        "pdf_url": "https://example.test/issue.pdf",
        "status": "page_out_of_range",
    }

    links = audit.pdf_page_links(record, pdf_pages=42)

    assert [link["page"] for link in links] == [40, 41, 42]


def test_pdf_page_links_for_single_page_include_previous_and_next():
    record = {
        "pdf_url": "https://example.test/issue.pdf",
        "pdf_page_start": 8,
        "pdf_page_end": 8,
    }

    links = audit.pdf_page_links(record, pdf_pages=20)

    assert [link["page"] for link in links] == [7, 8, 9]


def test_outer_matter_short_text_is_ignored():
    record = {
        "id": 10,
        "status": "ok",
        "text": "cover",
        "pdf_page_start": 1,
        "pdf_page_end": 1,
    }
    _, issues = audit.classify_record(record, default_args())

    filtered, reason = audit.ignore_outer_matter_issues(record, issues, pdf_pages=20)

    assert filtered == []
    assert reason == "outer_matter_page"


def test_missing_page_range_is_not_treated_as_outer_matter():
    record = {
        "id": 11,
        "status": "missing_page_range",
        "text": "",
    }
    _, issues = audit.classify_record(record, default_args())

    filtered, reason = audit.ignore_outer_matter_issues(record, issues, pdf_pages=20)

    assert [issue["code"] for issue in filtered] == ["empty_text"]
    assert reason is None
