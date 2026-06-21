import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import import_journal_issues as importer


def manifest_item(**overrides):
    item = {
        "journal_id": "aragonit",
        "journal_title": "Aragonit",
        "journal_short_title": "Aragonit",
        "issue_key": "29_1",
        "volume": "29",
        "year": 2024,
        "year_label": "2024",
        "issue": "1",
        "pdf_url": "https://example.test/aragonit.pdf",
        "pdf_page_offset": 2,
    }
    item.update(overrides)
    return item


def test_source_issue_key_uses_journal_and_manifest_issue_key():
    assert importer.source_issue_key(manifest_item()) == "aragonit:29_1"


def test_existing_source_issue_keys_detects_already_imported_issue():
    articles = [
        {"id": 1, "source_issue_key": "aragonit:29_1"},
        {"id": 2, "source_issue_key": "slovensky_kras:61_2023_2"},
    ]

    assert importer.existing_source_issue_keys(articles) == {
        "aragonit:29_1",
        "slovensky_kras:61_2023_2",
    }


def test_build_article_records_maps_printed_pages_to_physical_pages_and_sets_zero_offset():
    parsed = [
        {
            "title": "Prvý článok",
            "authors": ["Bella, P."],
            "pages": "51",
            "extras": ["1 obr."],
            "abstract": "Vecná anotácia prvého článku.",
            "caves": ["Zlepencová jaskyňa"],
            "has_map_plan": False,
        },
        {
            "title": "Druhý článok",
            "authors": ["Kudla, M."],
            "pages": "61",
            "extras": ["1 mapa"],
            "abstract": "Vecná anotácia druhého článku.",
            "caves": [],
            "has_map_plan": True,
        },
    ]

    records = importer.build_article_records(
        manifest_item(),
        parsed,
        start_id=100,
        printed_to_physical={51: 5, 60: 14, 61: 15},
        created_at="2026-06-19T00:00:00+00:00",
    )

    assert [record["id"] for record in records] == [100, 101]
    assert records[0]["pages"] == "51-60"
    assert records[0]["pdf_page_start"] == 5
    assert records[0]["pdf_page_end"] == 14
    assert records[0]["pdf_page_offset"] == 0
    assert records[0]["journal_id"] == "aragonit"
    assert records[0]["source_issue_key"] == "aragonit:29_1"
    assert records[0]["caves_verified"] is True

    assert records[1]["pages"] == "61"
    assert records[1]["pdf_page_start"] == 15
    assert records[1]["has_map_plan"] is True
    assert records[1]["map_plan_pages"] == [15]
    assert "mapa/plán" in records[1]["tags"]


def test_select_manifest_items_skips_existing_issue_keys_by_default():
    items = [
        manifest_item(issue_key="29_1"),
        manifest_item(issue_key="29_2"),
        manifest_item(journal_id="ine_publikacie", issue_key="book"),
    ]

    selected = importer.select_manifest_items(
        items,
        existing_keys={"aragonit:29_1"},
        journals={"aragonit", "slovensky_kras"},
    )

    assert [item["issue_key"] for item in selected] == ["29_2"]


def test_time_budget_exhausted_only_after_at_least_one_completed_issue():
    assert importer.time_budget_exhausted(start_monotonic=100.0, now_monotonic=400.0, max_seconds=240, completed=0) is False
    assert importer.time_budget_exhausted(start_monotonic=100.0, now_monotonic=400.0, max_seconds=240, completed=1) is True
    assert importer.time_budget_exhausted(start_monotonic=100.0, now_monotonic=200.0, max_seconds=240, completed=1) is False


def test_slovensky_kras_requires_toc_marker_before_ai_extraction():
    item = manifest_item(journal_id="slovensky_kras", issue_key="1_1958")

    assert importer.requires_toc_marker(item) is True
    assert importer.has_toc_marker("SLOVENSKÝ KRAS ACTA CARSOLOGICA") is False
    assert importer.has_toc_marker("OBSAH – CONTENTS ŠTÚDIE – STUDIES") is True


def test_select_toc_candidate_pages_prefers_edge_toc_pages_and_expands_neighbors():
    pages = [
        (1, "Titulná strana"),
        (2, "Úvodné údaje"),
        (3, "OBSAH\nAutor: Článok 5"),
        (20, "Text článku s obyčajným slovom obsah vo vete."),
        (99, "INHALT\nAuthor: German title 7"),
        (100, "CONTENTS\nAuthor: English title 7"),
        (101, "OBSAH\nAutor: Slovenský titul 7"),
    ]

    selected = importer.select_toc_candidate_pages(pages, fallback_pages=4, max_pages=7)

    assert selected == [2, 3, 4, 98, 99, 100, 101]


def test_extract_pdf_toc_text_from_page_provider_prefers_slovak_contents_first():
    texts = {
        1: "Titulná strana",
        98: "INHALT\nPavol Janáčik: Deutscher Titel 3",
        99: "CONTENTS\nPavol Janáčik: English title 3",
        100: "OBSAH\nPavol Janáčik: Slovenský titul 3",
    }

    text = importer.extract_pdf_toc_text_from_page_provider(
        page_count=100,
        fallback_pages=4,
        page_text=lambda page: texts.get(page, ""),
    )

    assert text.index("PDF PAGE 100") < text.index("PDF PAGE 98")
    assert "Slovenský titul" in text


def test_toc_like_structure_accepts_damaged_ocr_contents_without_heading():
    text = """
    COFLERKAHHE
    B. BeHHHKH: MccneflOBaHHe n p o n a c m Ha OrHHmTe 5
    A. Jíponna: ľeoMop<|>o.iiorHHecKHH xapaKTep n p o n a c T e n 14
    H. OTpy6a: TennoBOH peHtHM ^HflOBOH nponacTH 24
    V. Benický: Dokumentácia krasu a jaskýň 62
    L. Izák: Ochrana jaskýň 84
    """

    assert importer.toc_like_score(text) >= 8
    assert importer.has_toc_context(text) is True


def test_slovensky_kras_toc_import_requires_minimum_article_count():
    item = manifest_item(journal_id="slovensky_kras", issue_key="11_1973")

    assert importer.minimum_article_count_for_issue(item) == 4
    assert importer.minimum_article_count_for_issue(manifest_item(journal_id="aragonit")) == 1


def test_read_issue_key_file_accepts_manifest_toc_ready_json(tmp_path):
    path = tmp_path / "toc_ready.json"
    path.write_text('{"with_toc": ["4_1961-1962", "47_2009_1"], "without_toc": ["1_1958"]}', encoding="utf-8")

    assert importer.read_issue_key_file(path) == {"4_1961-1962", "47_2009_1"}
