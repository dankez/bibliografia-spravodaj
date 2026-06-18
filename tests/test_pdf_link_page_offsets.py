from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_pdf_links_use_global_two_page_offset():
    index_source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    detail_source = (ROOT / "web" / "src" / "pages" / "clanky" / "[id].astro").read_text(encoding="utf-8")

    assert ">= 2024 ? 2 : 0" not in index_source
    assert ">= 2024 ? 2 : 0" not in detail_source
    assert "PDF_PAGE_LINK_OFFSET = 2" in index_source
    assert "PDF_PAGE_LINK_OFFSET = 2" in detail_source
