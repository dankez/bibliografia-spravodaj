from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cave_routes_and_navigation_exist():
    caves_index = ROOT / "web" / "src" / "pages" / "jaskyne" / "index.astro"
    cave_detail = ROOT / "web" / "src" / "pages" / "jaskyne" / "[slug].astro"
    home_source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")

    assert caves_index.exists()
    assert cave_detail.exists()
    assert "Register jaskýň" in home_source


def test_mobile_navigation_and_search_controls_exist():
    home_source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    css_source = (ROOT / "web" / "src" / "styles" / "global.css").read_text(encoding="utf-8")

    assert 'id="mobile-menu-toggle"' in home_source
    assert 'id="mobile-search-toggle"' in home_source
    assert 'id="mobile-search-overlay"' in home_source
    assert 'id="mobile-search-input"' in home_source
    assert 'data-mobile-menu-link="jaskyne"' in home_source
    assert 'data-mobile-menu-link="exports"' in home_source
    assert "bibliographyExportMenus" in home_source
    assert "bibliografia_vsetko_danko" in home_source
    assert "bibliografia_aragonit_danko" in home_source
    assert "PDF" in home_source
    assert "bibliografia_slovensky_kras.sqlite" in home_source
    assert ".bibliography-export-menu-panel" in css_source
    assert '.bibliography-mobile-actions' in css_source
    assert '.mobile-theme-hidden' in css_source
    assert '.mobile-search-overlay.is-open' in css_source


def test_cave_timeline_shows_publication_and_alternates_sides():
    detail_source = (ROOT / "web" / "src" / "pages" / "jaskyne" / "[slug].astro").read_text(encoding="utf-8")
    css_source = (ROOT / "web" / "src" / "styles" / "global.css").read_text(encoding="utf-8")

    assert "article.journal_short_title" in detail_source
    assert "cave-timeline-side" in detail_source
    assert "--timeline-stagger-offset" in css_source
    assert "margin-top: var(--timeline-stagger-offset);" in css_source
    assert "cave-timeline-item:nth-child(odd)" in css_source
    assert "cave-timeline-item:nth-child(even)" in css_source
    assert "@media (max-width: 767px)" in css_source


def test_web_pages_hide_generic_import_abstracts():
    home_source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    article_detail = (ROOT / "web" / "src" / "pages" / "clanky" / "[id].astro").read_text(encoding="utf-8")
    cave_detail = (ROOT / "web" / "src" / "pages" / "jaskyne" / "[slug].astro").read_text(encoding="utf-8")

    assert "isGenericImportAbstract" in home_source
    assert "displayAbstract" in home_source
    assert "displayAbstract(article)" in home_source
    assert "isGenericImportAbstract" in article_detail
    assert "displayAbstract" in article_detail
    assert "isGenericImportAbstract" in cave_detail
    assert "displayAbstract(article)" in cave_detail


def test_article_detail_uses_current_journal_name_in_metadata():
    article_detail = (ROOT / "web" / "src" / "pages" / "clanky" / "[id].astro").read_text(encoding="utf-8")

    assert "{art.journal_short_title || 'Spravodaj SSS'} — {art.year}" in article_detail
    assert "Spravodajca SSS — {art.year}" not in article_detail


def test_theme_switcher_uses_day_night_labels():
    switcher_source = (ROOT / "web" / "src" / "components" / "ThemeSwitcher.astro").read_text(encoding="utf-8")

    assert "theme-switcher-icon" in switcher_source
    assert "sr-only" in switcher_source
    assert "Deň" in switcher_source
    assert "Noc" in switcher_source
    assert "Default" not in switcher_source
    assert "Dark" not in switcher_source


def test_brand_assets_are_used_for_home_banner_and_favicon():
    public_dir = ROOT / "web" / "public"
    home_source = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    layout_source = (ROOT / "web" / "src" / "layouts" / "Layout.astro").read_text(encoding="utf-8")
    css_source = (ROOT / "web" / "src" / "styles" / "global.css").read_text(encoding="utf-8")

    assert (public_dir / "brand" / "bibliografia-banner.png").exists()
    assert (public_dir / "brand" / "bibliografia-logo.png").exists()
    assert "/brand/bibliografia-banner.png" in home_source
    assert "/brand/bibliografia-logo.png" in home_source
    assert "/brand/bibliografia-logo.png" in layout_source
    assert "Autor:" in layout_source
    assert "DankeZ" in layout_source
    assert "https://github.com/dankez" in layout_source
    assert ".bibliography-brand-banner" in css_source
    assert ".bibliography-brand-logo" in css_source
    assert ".site-author-signature" in css_source


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
