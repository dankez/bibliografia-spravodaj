import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_cave_index


def test_build_cave_index_groups_articles_and_sorts_timeline():
    articles = [
        {
            "id": 2,
            "title": "Neskorší výskum",
            "year": 1980,
            "issue": "1",
            "pages": "20",
            "authors": ["Novák, J."],
            "abstract": "Pokračovanie.",
            "pdf_url": "https://example.test/1980.pdf",
            "pdf_page_start": 20,
            "caves": ["Domica"],
            "has_map_plan": True,
            "map_plan_pages": [22],
        },
        {
            "id": 1,
            "title": "Prvý výskum",
            "year": 1970,
            "issue": "2",
            "pages": "10-12",
            "authors": ["Kováč, P."],
            "abstract": "Začiatok.",
            "pdf_url": "https://example.test/1970.pdf",
            "pdf_page_start": 10,
            "caves": ["Domica", "Jasovská jaskyňa"],
        },
    ]

    caves = build_cave_index.build_cave_index(articles)

    domica = next(item for item in caves if item["name"] == "Domica")
    assert domica["slug"] == "domica"
    assert domica["article_count"] == 2
    assert domica["map_plan_count"] == 1
    assert domica["first_year"] == 1970
    assert domica["last_year"] == 1980
    assert domica["authors_count"] == 2
    assert [item["id"] for item in domica["articles"]] == [1, 2]
    assert domica["articles"][0]["pdf_link"] == "https://example.test/1970.pdf#page=12"

    jasov = next(item for item in caves if item["name"] == "Jasovská jaskyňa")
    assert jasov["article_count"] == 1


def test_current_cave_index_data_is_generated_for_web():
    caves_path = ROOT / "web" / "src" / "data" / "caves.json"
    assert caves_path.exists()
