from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_source(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    next_function = source.find("\n    function ", start + 1)
    return source[start:] if next_function == -1 else source[start:next_function]


def test_article_result_cards_do_not_interpolate_article_data_with_inner_html():
    source = (ROOT / "web/src/pages/index.astro").read_text(encoding="utf-8")
    render_list = _function_source(source, "renderList")

    assert "row.innerHTML" not in render_list
    assert "appendTextElement(row" in render_list
    assert "article.title" in render_list
    assert "displayAbstract(article)" in render_list


def test_local_errata_do_not_interpolate_user_text_with_inner_html():
    source = (ROOT / "web/src/pages/index.astro").read_text(encoding="utf-8")
    render_errata = _function_source(source, "renderErrata")

    assert "row.innerHTML" not in render_errata
    assert "${item.text}" not in render_errata
    assert "appendTextElement(row" in render_errata


def test_admin_errata_page_does_not_render_issue_text_with_inner_html():
    source = (ROOT / "web/src/pages/admin/opravy.astro").read_text(encoding="utf-8")

    assert "innerHTML" not in source
    assert "textContent" in source
    assert "document.createTextNode" in source
