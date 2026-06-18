from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cave_routes_and_navigation_exist():
    caves_index = ROOT / "web" / "src" / "pages" / "jaskyne" / "index.astro"
    cave_detail = ROOT / "web" / "src" / "pages" / "jaskyne" / "[slug].astro"
    home_source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")

    assert caves_index.exists()
    assert cave_detail.exists()
    assert "Register jaskýň" in home_source


def test_error_report_form_and_backend_template_exist_without_secret_literals():
    form_page = ROOT / "web" / "src" / "pages" / "nahlasit-chybu.astro"
    article_detail = ROOT / "web" / "src" / "pages" / "clanky" / "[id].astro"
    backend = ROOT / "web" / "functions" / "api" / "error-report.js"

    assert form_page.exists()
    assert backend.exists()

    form_source = form_page.read_text(encoding="utf-8")
    detail_source = article_detail.read_text(encoding="utf-8")
    backend_source = backend.read_text(encoding="utf-8")

    assert "Našiel som chybu" in detail_source
    assert "cf-turnstile" in form_source
    assert "turnstileToken" in backend_source
    assert "GITHUB_TOKEN" in backend_source
    assert "sk-" not in backend_source
    assert "ghp_" not in backend_source
