import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repair_article_metadata as repair


def test_repair_articles_uses_pdf_filename_for_year_and_issue():
    articles = [
        {
            "id": 1,
            "year": 2021,
            "issue": "kongres",
            "pdf_url": "https://sss.sk/wp-content/uploads/2021/05/Spravodaj_2013_kongres.pdf",
        },
        {
            "id": 2,
            "year": 2026,
            "issue": "3",
            "pdf_url": "https://sss.sk/wp-content/uploads/2026/01/Spravodaj_3_2025_web.pdf",
        },
        {
            "id": 3,
            "year": 2025,
            "issue": "2",
            "pdf_url": "https://sss.sk/wp-content/uploads/2025/10/Spravodaj_2_2025_net.pdf",
        },
    ]

    changes = repair.repair_articles(articles)

    assert [(item["id"], item["old"], item["new"]) for item in changes] == [
        (1, {"year": 2021, "issue": "kongres"}, {"year": 2013, "issue": "kongres"}),
        (2, {"year": 2026, "issue": "3"}, {"year": 2025, "issue": "3"}),
    ]
    assert articles[0]["year"] == 2013
    assert articles[0]["issue"] == "kongres"
    assert articles[1]["year"] == 2025
    assert articles[1]["issue"] == "3"
    assert articles[2]["year"] == 2025
    assert articles[2]["issue"] == "2"
