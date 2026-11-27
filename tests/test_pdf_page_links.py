import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_research_knowledge_db
import build_spravodaj_pdf_page_offsets
import extract_pdf_fulltext
import export_lalkovic_format
import export_public_sqlite
import pdf_page_links


def test_exporters_share_the_issue_specific_pdf_page():
    article = {
        "id": 120,
        "journal_id": "spravodaj_sss",
        "pages": "3-9",
        "pdf_page_start": 4,
        "pdf_url": "https://sss.sk/wp-content/uploads/2017/10/723.pdf",
    }

    assert pdf_page_links.linked_pdf_page(article) == 4
    assert export_public_sqlite.pdf_page(article) == 4
    assert export_lalkovic_format.pdf_link_page(article) == "4"
    assert build_research_knowledge_db.resolve_article_pdf_page_start(article) == 4


def test_linked_pdf_page_uses_each_spravodaj_issue_offset():
    cases = [
        (
            {
                "pages": "3-9",
                "pdf_page_start": 4,
                "pdf_url": "https://sss.sk/wp-content/uploads/2017/10/723.pdf",
            },
            4,
        ),
        (
            {
                "pages": "4-6",
                "pdf_page_start": 6,
                "pdf_url": "https://sss.sk/wp-content/uploads/2022/05/Spravodaj_SSS_4_1998.pdf",
            },
            6,
        ),
        (
            {
                "pages": "4-6",
                "pdf_page_start": 4,
                "pdf_url": "https://sss.sk/wp-content/uploads/2020/01/spravodaj2018_1.pdf",
            },
            6,
        ),
    ]

    for article, expected_page in cases:
        assert pdf_page_links.linked_pdf_page(article) == expected_page


def test_linked_pdf_page_preserves_physical_pages_for_imported_journals():
    article = {
        "journal_id": "aragonit",
        "pages": "51-60",
        "pdf_page_start": 5,
        "pdf_page_offset": 0,
    }

    assert pdf_page_links.linked_pdf_page(article) == 5


def test_spravodaj_links_handle_cover_pages_and_double_page_spreads():
    cases = [
        ("https://sss.sk/wp-content/uploads/2022/03/Spravodaj_SSS_1-2_1985.pdf", "1", 3),
        ("https://sss.sk/wp-content/uploads/2022/03/Spravodaj_SSS_1-2_1985.pdf", "3-7", 5),
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf", "4", 5),
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf", "45", 25),
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf", "65", 35),
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf", "82", 44),
    ]

    for url, pages, expected in cases:
        article = {"journal_id": "spravodaj_sss", "pdf_url": url, "pages": pages}
        assert pdf_page_links.linked_pdf_page(article) == expected
        assert build_research_knowledge_db.resolve_article_pdf_page_start(article) == expected


def test_spravodaj_links_handle_inserted_and_missing_pages_and_appendix():
    cases = [
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2010-2.pdf", "30", None, 32),
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2010-2.pdf", "31", None, 35),
        ("https://sss.sk/wp-content/uploads/2017/10/772.pdf", "3", None, 2),
        ("https://sss.sk/wp-content/uploads/2017/10/772.pdf", "20", None, 11),
        ("https://sss.sk/wp-content/uploads/2017/10/772.pdf", "21", None, 15),
        ("https://sss.sk/wp-content/uploads/2017/10/772.pdf", "25", None, 17),
        ("https://sss.sk/wp-content/uploads/2017/10/772.pdf", "35", None, 22),
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf", "82", 2814, 45),
        ("https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf", "3", None, 4),
        ("https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf", "11", None, 10),
        ("https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf", "35", None, 32),
        ("https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf", "67", None, 63),
        ("https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf", "79", None, 73),
        ("https://sss.sk/wp-content/uploads/2022/02/Spravodaj_SSS_1983_1.pdf", "1", 553, 3),
        ("https://sss.sk/wp-content/uploads/2022/02/Spravodaj_SSS_1983_1.pdf", "1", 569, 45),
    ]
    for url, pages, article_id, expected in cases:
        article = {"id": article_id, "pdf_url": url, "pages": pages}
        assert pdf_page_links.linked_pdf_page(article) == expected
        assert build_research_knowledge_db.resolve_article_pdf_page_start(article) == expected


def test_non_linear_ranges_resolve_both_endpoints():
    for url, pages, start, end in [
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf", "44-46", 25, 26),
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf", "58-64", 32, 35),
        ("https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2010-2.pdf", "29-33", 31, 37),
        ("https://sss.sk/wp-content/uploads/2017/10/772.pdf", "20-21", 11, 15),
        ("https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf", "64-67", 60, 63),
    ]:
        article = {"pdf_url": url, "pages": pages}
        printed_start, printed_end = extract_pdf_fulltext.parse_page_range(pages)
        assert build_research_knowledge_db.resolve_article_pdf_page_end(article) == end
        assert extract_pdf_fulltext.resolve_article_physical_page_range(
            article, printed_start, printed_end, {printed_start: 1}, pdf_pages=100
        ) == (start, end, None)


def test_offset_builder_uses_consensus_and_preserves_existing_mappings(tmp_path, monkeypatch):
    builder = build_spravodaj_pdf_page_offsets
    urls = ["https://example.com/new.pdf", "https://example.com/verified.pdf"]
    for url in urls:
        (tmp_path / builder.safe_name(url)).touch()
    special = {"offset": 3, "divisor": 2}
    monkeypatch.setattr(builder, "PDF_CACHE_DIR", tmp_path)
    monkeypatch.setattr(builder, "load_pdf_page_offsets", lambda: {urls[1]: special})
    monkeypatch.setattr(
        builder, "infer_printed_page_map",
        lambda *args, **kwargs: {1: 1, 3: 5, 4: 6, 5: 7, 6: 8},
    )
    mappings, fallbacks = builder.build_offsets([{"pdf_url": url, "pages": "1"} for url in urls])
    assert mappings == {urls[0]: 2, urls[1]: special}
    assert fallbacks == []


def test_slovensky_kras_import_links_to_the_actual_article_start():
    for path in [ROOT / "data" / "articles_with_urls.json", ROOT / "web" / "src" / "data" / "articles.json"]:
        articles = json.loads(path.read_text(encoding="utf-8"))
        article = next(article for article in articles if article["id"] == 5702)
        assert pdf_page_links.linked_pdf_page(article) == 108


def test_corrected_articles_link_to_verified_pages():
    for path in [ROOT / "data" / "articles_with_urls.json", ROOT / "web" / "src" / "data" / "articles.json"]:
        articles = {article["id"]: article for article in json.loads(path.read_text(encoding="utf-8"))}
        for article_id, expected_page in [(1502, 31), (2814, 45), (3993, 5), (3994, 8), (4133, 1), (4134, 4), (4135, 10), (4136, 19)]:
            assert pdf_page_links.linked_pdf_page(articles[article_id]) == expected_page
