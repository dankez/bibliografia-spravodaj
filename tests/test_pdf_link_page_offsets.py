from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_pdf_links_use_shared_issue_page_resolver():
    index_source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    detail_source = (ROOT / "web" / "src" / "pages" / "clanky" / "[id].astro").read_text(encoding="utf-8")

    assert ">= 2024 ? 2 : 0" not in index_source
    assert ">= 2024 ? 2 : 0" not in detail_source
    assert "getPdfPageNumber(article, issuePageOffsets)" in index_source
    assert "getPdfPageNumber(art, issuePageOffsets)" in detail_source
