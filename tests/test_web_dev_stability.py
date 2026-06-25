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


def test_browser_fulltext_index_is_scope_limited_for_mobile_performance():
    index_page = (ROOT / "web/src/pages/index.astro").read_text(encoding="utf-8")

    assert "FULLTEXT_MAX_EAGER_SHARDS" in index_page
    assert "FULLTEXT_MAX_EAGER_BYTES" in index_page
    assert "function isFulltextScopeTooLarge" in index_page
    assert "fulltextLoadState = 'limited'" in index_page
    assert "zúžte časopis alebo roky" in index_page
    assert "Promise.all(missingShards.map(loadFulltextShard))" in index_page
    assert "Promise.all(fulltextRelevantShards(manifest).map(loadFulltextShard))" not in index_page
