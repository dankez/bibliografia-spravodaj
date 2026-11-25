import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_research_knowledge_db
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
