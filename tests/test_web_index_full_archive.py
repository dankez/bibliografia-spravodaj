import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_index_uses_full_multi_journal_archive_instead_of_test_year_slice():
    source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    articles = json.loads((ROOT / "web" / "src" / "data" / "articles.json").read_text(encoding="utf-8"))

    assert min(article["year"] for article in articles) == 1958
    assert max(article["year"] for article in articles) >= 2026
    assert "TEST_START_YEAR" not in source
    assert "latestArticles" not in source
    assert "Článkov 2024+" not in source
    assert "Kompletný archív ročníkov {startYear}-{endYear}" in source
