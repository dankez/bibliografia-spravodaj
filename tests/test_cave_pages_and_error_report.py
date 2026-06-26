from pathlib import Path
import json

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
    assert "TLAČ" in home_source
    assert "_tlac.html" in home_source
    assert "bibliography-export-printer-icon" in home_source
    assert "bibliografia_slovensky_kras.sqlite" in home_source
    assert ".bibliography-export-menu-panel" in css_source
    assert '.bibliography-mobile-actions' in css_source
    assert '.mobile-theme-hidden' in css_source
    assert '.mobile-search-overlay.is-open' in css_source


def test_cave_timeline_shows_publication_and_alternates_sides():
    detail_source = (ROOT / "web" / "src" / "pages" / "jaskyne" / "[slug].astro").read_text(encoding="utf-8")
    css_source = (ROOT / "web" / "src" / "styles" / "global.css").read_text(encoding="utf-8")

    assert "article.journal_short_title" in detail_source
    assert "smopaj_cave_number" in detail_source
    assert "Číslo jaskyne" in detail_source
    assert "cave-timeline-side" in detail_source
    assert "--timeline-stagger-offset" in css_source
    assert "margin-top: var(--timeline-stagger-offset);" in css_source
    assert "cave-timeline-item:nth-child(odd)" in css_source
    assert "cave-timeline-item:nth-child(even)" in css_source
    assert "@media (max-width: 767px)" in css_source
    assert "Doplniť číslo jaskyne" in detail_source
    assert "smopaj_number" in detail_source


def test_cave_register_cards_show_official_smopaj_cave_number():
    index_source = (ROOT / "web" / "src" / "pages" / "jaskyne" / "index.astro").read_text(encoding="utf-8")

    assert "smopaj_cave_number" in index_source
    assert "Číslo jaskyne" in index_source


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

    assert (public_dir / "brand" / "bibliografia-banner-ui-sm.webp").exists()
    assert (public_dir / "brand" / "bibliografia-banner-ui-md.webp").exists()
    assert (public_dir / "brand" / "bibliografia-banner-ui.webp").exists()
    assert (public_dir / "brand" / "bibliografia-banner.png").exists()
    assert (public_dir / "brand" / "bibliografia-logo-mobile.webp").exists()
    assert (public_dir / "brand" / "bibliografia-logo-mobile-256.webp").exists()
    assert (public_dir / "brand" / "bibliografia-logo-ui.webp").exists()
    assert (public_dir / "brand" / "bibliografia-icon.png").exists()
    assert (public_dir / "brand" / "bibliografia-logo.png").exists()
    assert "/brand/bibliografia-banner-ui-sm.webp" in home_source
    assert "/brand/bibliografia-logo-mobile.webp" in home_source
    assert "/brand/bibliografia-logo-mobile-256.webp" in home_source
    assert "/brand/bibliografia-icon.png" in layout_source
    assert "Autor:" in layout_source
    assert "DankeZ" in layout_source
    assert "https://github.com/dankez" in layout_source
    assert ".bibliography-brand-banner" in css_source
    assert ".bibliography-brand-logo" in css_source
    assert ".site-author-signature" in css_source


def test_llms_txt_is_markdown_with_h1():
    llms = (ROOT / "web" / "public" / "llms.txt").read_text(encoding="utf-8")

    assert llms.startswith("# Digitálna bibliografia")
    assert "## Preferované použitie" in llms
    assert "https://github.com/dankez" in llms


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
    assert "smopaj_number" in form_source
    assert "smopaj_number" in backend_source
    assert "smopaj_cave_register_2017_search.json" in form_source
    assert "smopajCaveNumber" in backend_source
    assert "Číslo jaskyne / SMOPaJ" in backend_source
    assert "GITHUB_TOKEN" in backend_source
    assert "sk-" not in backend_source
    assert "ghp_" not in backend_source


def test_admin_errata_page_and_backend_use_password_session_auth():
    admin_page = ROOT / "web" / "src" / "pages" / "admin" / "opravy.astro"
    admin_backend_files = [
        ROOT / "web" / "functions" / "_lib" / "admin-auth.js",
        ROOT / "web" / "functions" / "api" / "admin" / "errata.js",
        ROOT / "web" / "functions" / "api" / "admin" / "login.js",
        ROOT / "web" / "functions" / "api" / "admin" / "logout.js",
        ROOT / "web" / "functions" / "api" / "admin" / "session.js",
    ]
    admin_apply_script = ROOT / "scripts" / "apply_errata_issue.py"
    admin_workflow = ROOT / ".github" / "workflows" / "approve-errata.yml"

    assert admin_page.exists()
    for admin_backend in admin_backend_files:
        assert admin_backend.exists()
    assert admin_apply_script.exists()
    assert admin_workflow.exists()

    page_source = admin_page.read_text(encoding="utf-8")
    backend_source = "\n".join(path.read_text(encoding="utf-8") for path in admin_backend_files)
    apply_source = admin_apply_script.read_text(encoding="utf-8")
    workflow_source = admin_workflow.read_text(encoding="utf-8")

    assert "/api/admin/errata" in page_source
    assert "/api/admin/login" in page_source
    assert "/api/admin/logout" in page_source
    assert "/api/admin/session" in page_source
    assert "noindex, nofollow" in page_source
    assert "Admin login" in page_source
    assert "Cloudflare Access" not in page_source
    assert "credentials: 'same-origin'" in page_source
    assert "sessionStorage" not in page_source
    assert "Schváliť opravu a zapísať do webu" in page_source
    assert "Otvoriť workflow" in page_source
    assert "textContent" in page_source
    assert "innerHTML" not in page_source
    assert "ADMIN_PASSWORD_HASH" in backend_source
    assert "SESSION_SECRET" in backend_source
    assert "Set-Cookie" in backend_source
    assert "HttpOnly" in backend_source
    assert "SameSite=Strict" in backend_source
    assert "SHA-256" in backend_source
    assert "HMAC" in backend_source
    assert "timingSafeEqual" in backend_source
    assert "GITHUB_TOKEN" in backend_source
    assert "dispatchApprovalWorkflow" in backend_source
    assert "/actions/workflows/" in backend_source
    assert "approve-errata.yml" in backend_source
    assert "data/articles_with_urls.json" in apply_source
    assert "web/src/data/articles.json" in apply_source
    assert "scripts/apply_errata_issue.py" in workflow_source
    assert "sk-" not in backend_source
    assert "ghp_" not in backend_source


def test_public_smopaj_cave_register_search_index_contains_official_numbers():
    public_register = ROOT / "web" / "public" / "data" / "smopaj_cave_register_2017_search.json"

    assert public_register.exists()
    payload = json.loads(public_register.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "smopaj-cave-public-search/v1"
    assert payload["stats"]["entries"] == 7329
    by_number = {entry["cave_number"]: entry for entry in payload["entries"]}
    assert by_number["3483.1"]["official_name"] == "Domica"
    assert by_number["3483.1"]["geomorph_celok"] == "Slovenský kras"
    assert "Baradla" in by_number["3483.1"]["names"]
