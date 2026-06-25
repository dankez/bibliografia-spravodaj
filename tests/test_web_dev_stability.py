from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_homepage_client_script_does_not_bundle_large_articles_json():
    index_page = (ROOT / "web/src/pages/index.astro").read_text(encoding="utf-8")
    assert "import articlesRaw from '../data/articles.json'" not in index_page
    assert "ARTICLES_DATA_URL" in index_page
    assert "fetch(ARTICLES_DATA_URL)" in index_page
    assert "document.readyState === 'loading'" in index_page


def test_vite_prebundles_minisearch_for_stable_dev_startup():
    astro_config = (ROOT / "web/astro.config.mjs").read_text(encoding="utf-8")
    assert "optimizeDeps" in astro_config
    assert "minisearch" in astro_config


def test_articles_json_endpoint_exists_for_client_fetch():
    endpoint = ROOT / "web/src/pages/data/articles.json.ts"
    assert endpoint.exists()
    content = endpoint.read_text(encoding="utf-8")
    assert "export const prerender = true" in content
    assert "Content-Type" in content


def test_browser_fulltext_index_loads_all_on_desktop_and_batches_on_mobile():
    index_page = (ROOT / "web/src/pages/index.astro").read_text(encoding="utf-8")

    assert "FULLTEXT_MOBILE_BATCH_SHARDS" in index_page
    assert "function loadFulltextShardsInMobileBatches" in index_page
    assert "fulltextLoadState = 'batching'" in index_page
    assert "isMobileViewport() && missingShards.length > FULLTEXT_MOBILE_BATCH_SHARDS" in index_page
    assert "Promise.all(missingShards.map(loadFulltextShard))" in index_page
    assert "FULLTEXT_MAX_EAGER" not in index_page
    assert "fulltextLoadState = 'limited'" not in index_page
    assert "zúžte časopis alebo roky" not in index_page


def test_mobile_brand_uses_small_transparent_assets():
    index_page = (ROOT / "web/src/pages/index.astro").read_text(encoding="utf-8")
    layout_page = (ROOT / "web/src/layouts/Layout.astro").read_text(encoding="utf-8")
    mobile_logo = ROOT / "web/public/brand/bibliografia-logo-ui.webp"
    icon = ROOT / "web/public/brand/bibliografia-icon.png"

    assert 'src="/brand/bibliografia-logo-ui.webp"' in index_page
    assert 'href="/brand/bibliografia-icon.png"' in layout_page
    assert mobile_logo.exists()
    assert icon.exists()
    assert mobile_logo.stat().st_size < 32 * 1024
    assert icon.stat().st_size < 32 * 1024
