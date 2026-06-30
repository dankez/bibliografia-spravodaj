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


def test_resolve_article_physical_page_range_uses_imported_journal_pages():
    article = {
        "journal_id": "aragonit",
        "pages": "51-60",
        "pdf_page_start": 5,
        "pdf_page_end": 14,
        "pdf_page_offset": 0,
    }

    start, end, error = fulltext.resolve_article_physical_page_range(
        article,
        51,
        60,
        {},
        pdf_pages=80,
    )

    assert error is None
    assert (start, end) == (5, 14)


def test_resolve_article_physical_page_range_falls_back_to_legacy_offset():
    article = {"pages": "57", "pdf_page_offset": 2}

    start, end, error = fulltext.resolve_article_physical_page_range(
        article,
        57,
        57,
        {},
        pdf_pages=90,
    )

    assert error is None
    assert (start, end) == (59, 59)


def test_resolve_article_physical_page_range_uses_aragonit_offset_without_imported_page():
    article = {"journal_id": "aragonit", "pages": "47-48", "pdf_page_offset": 0}

    start, end, error = fulltext.resolve_article_physical_page_range(
        article,
        47,
        48,
        {},
        pdf_pages=80,
    )

    assert error is None
    assert (start, end) == (49, 50)


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


def test_infer_printed_page_number_handles_mixed_spravodaj_footer():
    text = """
    Text článku
    Organizačné správy SSS                               98                             Spravodaj SSS 1/2026
    """

    assert fulltext.infer_printed_page_number(text) == 98


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


def test_text_quality_metrics_flags_missing_diacritic_tokens():
    text = "Zahranicné cesty, ked clovek pozviechat sily a riaditel povie Ved."

    metrics = fulltext.text_quality_metrics(text)

    assert metrics["bad_diacritic_token_count"] >= 5
    assert "Zahranicné" in metrics["bad_diacritic_token_examples"]


def test_should_reocr_text_layer_uses_font_unicode_and_bad_tokens():
    text = (
        "Zahranicné pracovné cesty sú vždy inšpiratívne. "
        "Najmä ked clovek zapochybuje, ci vie pozviechat sily. "
        "Ved súcasnost vyžaduje cinnost a starostlivost. "
    ) * 8
    metrics = fulltext.text_quality_metrics(text)
    font_summary = {"all_fonts_without_unicode_map": True}

    should_ocr, reason = fulltext.should_reocr_text_layer(
        text,
        metrics,
        font_summary,
        min_bad_tokens=4,
        min_chars=600,
    )

    assert should_ocr is True
    assert reason == "font_unicode_map_missing_and_bad_tokens"


def test_should_reocr_text_layer_does_not_judge_short_text():
    metrics = fulltext.text_quality_metrics("ked clovek")

    should_ocr, reason = fulltext.should_reocr_text_layer(
        "ked clovek",
        metrics,
        {"all_fonts_without_unicode_map": True},
        min_bad_tokens=1,
        min_chars=600,
    )

    assert should_ocr is False
    assert reason == "too_short_to_judge"


def test_choose_ocr_text_accepts_replacement_with_fewer_bad_tokens():
    original = "Zahranicné cesty ked clovek ci oci Ved riaditel." * 20
    replacement = "Zahraničné cesty keď človek či oči Veď riaditeľ." * 20

    use_ocr, reason = fulltext.choose_ocr_text(original, replacement, "bad-text")

    assert use_ocr is True
    assert reason == "fewer_bad_tokens"


def test_choose_ocr_text_accepts_shorter_layout_with_comparable_words():
    original = ("Zahranicné                cesty                ked                clovek                ci                oci. " * 120).strip()
    replacement = ("Zahraničné cesty keď človek či oči. " * 120).strip()

    use_ocr, reason = fulltext.choose_ocr_text(original, replacement, "bad-text")

    assert use_ocr is True
    assert reason == "fewer_bad_tokens_with_comparable_words"


def test_pdffonts_summary_detects_missing_unicode_maps(monkeypatch):
    class Result:
        returncode = 0
        stderr = ""
        stdout = """name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
Times-Roman                          TrueType          WinAnsi          no  no  no     196  0
Helvetica                            TrueType          WinAnsi          no  no  no     197  0
"""

    monkeypatch.setattr(fulltext.subprocess, "run", lambda *args, **kwargs: Result())

    summary = fulltext.pdffonts_summary(Path("issue.pdf"))

    assert summary["font_rows"] == 2
    assert summary["encodings"] == {"WinAnsi": 2}
    assert summary["unicode_maps"] == {"no": 2}
    assert summary["all_fonts_without_unicode_map"] is True


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
