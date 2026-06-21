import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_public_exports as exporter


def test_export_scopes_include_combined_and_each_journal():
    scopes = {scope["id"]: scope for scope in exporter.EXPORT_SCOPES}

    assert set(scopes) == {"all", "spravodaj_sss", "aragonit", "slovensky_kras"}
    assert scopes["all"]["basename"] == "bibliografia_vsetko_danko"
    assert scopes["all"]["group_by_journal"] is True
    assert scopes["aragonit"]["sqlite"] == "bibliografia_aragonit.sqlite"
    assert "group_by_journal" not in scopes["aragonit"]
    assert scopes["slovensky_kras"]["title"] == "Bibliografia časopisu Slovenský kras"


def test_scope_articles_uses_spravodaj_default_for_legacy_records():
    articles = [
        {"id": 1, "title": "Legacy Spravodaj"},
        {"id": 2, "journal_id": "aragonit", "title": "Aragonit"},
        {"id": 3, "journal_id": "slovensky_kras", "title": "Slovenský kras"},
    ]
    scopes = {scope["id"]: scope for scope in exporter.EXPORT_SCOPES}

    assert [article["id"] for article in exporter.scope_articles(articles, scopes["all"])] == [1, 2, 3]
    assert [article["id"] for article in exporter.scope_articles(articles, scopes["spravodaj_sss"])] == [1]
    assert [article["id"] for article in exporter.scope_articles(articles, scopes["aragonit"])] == [2]
    assert [article["id"] for article in exporter.scope_articles(articles, scopes["slovensky_kras"])] == [3]
