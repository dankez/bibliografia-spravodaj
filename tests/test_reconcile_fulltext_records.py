import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import reconcile_fulltext_records as reconcile


def test_select_best_prefers_ok_text_over_empty_error():
    bad = {
        "_line": 1,
        "id": 10,
        "status": "page_out_of_range",
        "text": "",
        "title": "A",
    }
    good = {
        "_line": 2,
        "id": 10,
        "status": "ok",
        "text": "Dostatocny text clanku " * 20,
        "text_chars": 500,
        "title": "A",
    }

    assert reconcile.select_best([bad, good]) is good


def test_select_best_prefers_tesseract_when_quality_is_otherwise_equal():
    pdftotext = {
        "_line": 1,
        "id": 20,
        "status": "ok",
        "text": "Rovnaky text " * 40,
        "text_source": "pdftotext",
    }
    ocr = {
        "_line": 2,
        "id": 20,
        "status": "ok",
        "text": "Rovnaky text " * 40,
        "text_source": "tesseract_ocr",
    }

    assert reconcile.select_best([pdftotext, ocr]) is ocr


def test_reconcile_dedupes_in_article_order_and_reports_missing():
    articles = [{"id": 1}, {"id": 2}, {"id": 3}]
    records = [
        {"_line": 1, "id": 2, "status": "page_out_of_range", "text": ""},
        {"_line": 2, "id": 1, "status": "ok", "text": "Prvy clanok " * 20},
        {"_line": 3, "id": 2, "status": "ok", "text": "Druhy clanok " * 20},
    ]

    output, report = reconcile.reconcile(records, articles)

    assert [record["id"] for record in output] == [1, 2]
    assert output[1]["_line"] == 3
    assert report["summary"]["removed_records"] == 1
    assert report["summary"]["duplicate_article_ids"] == 1
    assert report["summary"]["missing_fulltext_for_articles"] == 1
    assert report["missing_article_ids"] == [3]
