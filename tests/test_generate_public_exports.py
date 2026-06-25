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
    assert "legacy_basename" not in scopes["all"]
    assert "legacy_sqlite" not in scopes["all"]
    assert scopes["spravodaj_sss"]["legacy_basename"] == "spravodaj_sss_danko"
    assert scopes["spravodaj_sss"]["legacy_sqlite"] == "spravodaj_sss.sqlite"
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


def test_copy_danko_exports_includes_print_html_and_legacy_names(tmp_path):
    data_export_dir = tmp_path / "data"
    web_export_dir = tmp_path / "web"
    scope = {
        "basename": "bibliografia_spravodaj_sss_danko",
        "legacy_basename": "spravodaj_sss_danko",
    }
    for extension in ("txt", "md", "html", "pdf"):
        path = data_export_dir / f"bibliografia_spravodaj_sss_danko.{extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(extension, encoding="utf-8")
    (data_export_dir / "bibliografia_spravodaj_sss_danko_tlac.html").write_text("print", encoding="utf-8")

    exporter.copy_danko_exports(
        scope=scope,
        data_export_dir=data_export_dir,
        web_export_dir=web_export_dir,
    )

    assert (web_export_dir / "bibliografia_spravodaj_sss_danko_tlac.html").read_text(encoding="utf-8") == "print"
    assert (data_export_dir / "spravodaj_sss_danko_tlac.html").read_text(encoding="utf-8") == "print"
    assert (web_export_dir / "spravodaj_sss_danko_tlac.html").read_text(encoding="utf-8") == "print"
