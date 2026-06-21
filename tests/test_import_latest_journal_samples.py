import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import import_latest_journal_samples as importer


def test_build_sample_issue_articles_imports_latest_aragonit_and_slovensky_kras():
    articles = importer.build_sample_issue_articles(start_id=3803)

    assert len(articles) == 19
    assert [article["id"] for article in articles] == list(range(3803, 3822))

    aragonit = [article for article in articles if article["journal_id"] == "aragonit"]
    kras = [article for article in articles if article["journal_id"] == "slovensky_kras"]

    assert len(aragonit) == 12
    assert len(kras) == 7

    assert aragonit[0]["title"] == "Jaskyňa vytvorená na rozhraní karbonatických zlepencov a slieňovcov, Zuberecká brázda na úpätí Západných Tatier"
    assert aragonit[0]["authors"] == ["Littva, J.", "Bella, P.", "Herich, P.", "Soták, J.", "Danielčáková, I."]
    assert aragonit[0]["year"] == 2024
    assert aragonit[0]["pages"] == "51-60"
    assert aragonit[0]["pdf_page_start"] == 5
    assert aragonit[0]["pdf_page_offset"] == 0
    assert aragonit[0]["abstract"] == ""
    assert aragonit[0]["abstract_source"] == "missing"

    assert kras[0]["title"] == "Fosílne, subfosílne až recentné nálezy stavovcov (Vertebrata) z jaskynných lokalít na Slovensku"
    assert kras[0]["authors"] == ["Čeklovský, T.", "Farkašovská, E.", "Obuch, J."]
    assert kras[0]["year"] == 2023
    assert kras[0]["pages"] == "101-118"
    assert kras[0]["pdf_page_start"] == 5
    assert kras[0]["pdf_page_offset"] == 0
    assert kras[0]["abstract"] == ""
    assert kras[0]["abstract_source"] == "missing"

    assert all(article["caves_verified"] for article in articles if article["caves"])


def test_merge_sample_articles_is_idempotent_for_same_issue_keys():
    existing = [
        {"id": 1, "title": "Pôvodný článok"},
        {
            "id": 99,
            "title": "Starý import",
            "created_by": importer.CREATED_BY,
            "source_issue_key": "aragonit:29_2",
        },
    ]

    merged = importer.merge_sample_articles(existing)
    merged_again = importer.merge_sample_articles(merged)

    assert len(merged) == len(merged_again)
    assert sum(1 for article in merged if article.get("source_issue_key") == "aragonit:29_2") == 12
    assert merged[0]["id"] == 1
    assert min(article["id"] for article in merged if article.get("created_by") == importer.CREATED_BY) == 2


def test_journal_filter_replaces_issue_filter_on_web_homepage():
    source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")

    assert "journal-filter-select" in source
    assert "Filter časopisu" in source
    assert "issue-filter-btn" not in source
    assert "state.journal" in source
    assert "state.issue" not in source
    assert "selectedStillVisible" in source
    assert "clearSelectedArticle" in source
