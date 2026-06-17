import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_pdf_fulltext as fulltext


def test_resolve_physical_page_range_falls_back_when_mapped_end_goes_backwards():
    start, end, error = fulltext.resolve_physical_page_range(
        18,
        20,
        {18: 18, 20: 11},
        pdf_pages=24,
    )

    assert error is None
    assert (start, end) == (18, 20)


def test_resolve_physical_page_range_reports_start_after_pdf_end():
    start, end, error = fulltext.resolve_physical_page_range(
        72,
        72,
        {},
        pdf_pages=51,
    )

    assert (start, end) == (None, None)
    assert error == "page_out_of_range"


def test_empty_text_probe_ranges_try_following_pages_for_unmapped_printed_page():
    ranges = fulltext.empty_text_probe_ranges(
        physical_start=1,
        physical_end=1,
        printed_start=1,
        page_map={3: 5},
        pdf_pages=6,
        max_probe=3,
    )

    assert ranges == [(2, 2), (3, 3), (4, 4)]


def test_empty_text_probe_ranges_skip_mapped_printed_page():
    ranges = fulltext.empty_text_probe_ranges(
        physical_start=1,
        physical_end=1,
        printed_start=1,
        page_map={1: 1},
        pdf_pages=6,
    )

    assert ranges == []


def test_article_text_score_prefers_author_and_abstract_matches():
    article = {
        "title": "Úvodník",
        "authors": ["Kladiva, E."],
        "abstract": "O charaktere čísla a potenciálnych dopisovateľoch",
    }

    cover_score = fulltext.article_text_score("Farebné fotografie na obálke", article)
    article_score = fulltext.article_text_score(
        "Edo Kladiva píše o dopisovateľoch a charaktere čísla.",
        article,
    )

    assert cover_score == 0
    assert article_score > cover_score


def test_sync_article_page_links_clears_invalid_fulltext_records(tmp_path):
    fulltext_path = tmp_path / "article_fulltext.jsonl"
    articles_path = tmp_path / "articles.json"
    frontend_path = tmp_path / "frontend.json"
    articles = [
        {"id": 1, "pdf_page_start": 10, "pdf_page_end": 10},
        {"id": 2, "pdf_page_start": None, "pdf_page_end": None},
    ]
    articles_path.write_text(json.dumps(articles), encoding="utf-8")
    frontend_path.write_text(json.dumps(articles), encoding="utf-8")
    rows = [
        {"id": 1, "status": "page_out_of_range", "pdf_page_start": 72, "pdf_page_end": 72},
        {"id": 2, "status": "ok", "pdf_page_start": 5, "pdf_page_end": 6},
    ]
    fulltext_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    updated = fulltext.sync_article_page_links(fulltext_path, articles_path, frontend_path)
    synced = json.loads(articles_path.read_text(encoding="utf-8"))

    assert updated == 2
    assert synced[0]["pdf_page_start"] is None
    assert synced[0]["pdf_page_end"] is None
    assert synced[1]["pdf_page_start"] == 5
