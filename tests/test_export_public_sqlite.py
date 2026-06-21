import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_public_sqlite as public_sqlite


def sample_articles():
    return [
        {
            "id": 3413,
            "authors": ["Anonymus"],
            "title": "Oblastná skupina Orava",
            "year": 2021,
            "volume": "I.",
            "issue": "2",
            "pages": "57",
            "abstract": "Prehľad činnosti Oblastnej skupiny Orava.",
            "pdf_url": "https://sss.sk/wp-content/uploads/2023/01/Spravodaj_SSS_2_2021.pdf",
            "pdf_page_start": 57,
            "caves": ["Domica"],
            "tags": ["výročná správa"],
            "groups": ["Orava"],
            "has_map_plan": True,
            "map_plan_pages": [59],
        },
        {
            "id": 10,
            "authors": ["Roda, Š.", "Kámen, S."],
            "title": "100 rokov Dobšinskej ľadovej jaskyne",
            "year": 1970,
            "volume": "I.",
            "issue": "2",
            "pages": "13-19",
            "abstract": "Konferencia a exkurzie.",
            "pdf_url": "https://sss.sk/wp-content/uploads/2017/10/702.pdf",
            "pdf_page_start": 13,
            "caves": ["Dobšinská ľadová jaskyňa"],
            "tags": ["dejiny"],
            "groups": [],
        },
        {
            "id": 9001,
            "journal_id": "slovensky_kras",
            "journal_title": "Slovenský kras",
            "authors": ["Bella, P."],
            "title": "Geomorfologické procesy v jaskyniach",
            "year": 2009,
            "volume": "47",
            "issue": "1",
            "pages": "5-39",
            "abstract": "Štúdia o geomorfologických procesoch v jaskyniach.",
            "pdf_url": "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/47_2009_1.pdf",
            "pdf_page_start": 5,
            "pdf_page_offset": 0,
            "caves": [],
            "tags": [],
            "groups": [],
        },
    ]


def test_export_database_creates_research_friendly_tables(tmp_path):
    db_path = tmp_path / "spravodaj_sss.sqlite"

    summary = public_sqlite.export_database(sample_articles(), db_path)

    assert summary == {
        "articles": 3,
        "journals": 2,
        "authors": 4,
        "caves": 2,
        "tags": 2,
        "groups": 1,
        "map_plan_articles": 1,
    }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "articles",
            "authors",
            "article_authors",
            "caves",
            "article_caves",
            "tags",
            "article_tags",
            "groups",
            "article_groups",
            "map_plans",
            "export_metadata",
            "journals",
        }.issubset(tables)

        article = conn.execute("SELECT * FROM articles WHERE id = 3413").fetchone()
        assert article["title"] == "Oblastná skupina Orava"
        assert article["pdf_page"] == 59
        assert article["pdf_link"] == "https://sss.sk/wp-content/uploads/2023/01/Spravodaj_SSS_2_2021.pdf#page=59"

        authors = conn.execute(
            """
            SELECT a.name
            FROM authors a
            JOIN article_authors aa ON aa.author_id = a.id
            WHERE aa.article_id = 10
            ORDER BY aa.position
            """
        ).fetchall()
        assert [row["name"] for row in authors] == ["Roda, Š.", "Kámen, S."]

        map_row = conn.execute("SELECT * FROM map_plans WHERE article_id = 3413").fetchone()
        assert json.loads(map_row["pages_json"]) == [59]

        spravodaj_journal = conn.execute("SELECT * FROM journals WHERE id = 'spravodaj_sss'").fetchone()
        assert spravodaj_journal["title"] == "Spravodaj Slovenskej speleologickej spoločnosti"

        kras_article = conn.execute("SELECT * FROM articles WHERE id = 9001").fetchone()
        assert kras_article["journal_id"] == "slovensky_kras"
        assert kras_article["journal_title"] == "Slovenský kras"
        assert kras_article["pdf_page"] == 5
        assert kras_article["pdf_link"] == "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/47_2009_1.pdf#page=5"
    finally:
        conn.close()
