from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cloudflare_pages_headers_are_versioned_in_public_assets():
    headers_path = ROOT / "web/public/_headers"
    assert headers_path.exists()
    headers = headers_path.read_text(encoding="utf-8")

    assert "/*" in headers
    assert "X-Content-Type-Options: nosniff" in headers
    assert "Referrer-Policy: strict-origin-when-cross-origin" in headers
    assert "Permissions-Policy:" in headers
    assert "Content-Security-Policy:" in headers
    assert "base-uri 'self'" in headers
    assert "object-src 'none'" in headers
    assert "frame-ancestors 'self' https://sss.sk https://www.sss.sk" in headers


def test_cloudflare_pages_preview_domain_is_not_indexed():
    headers = (ROOT / "web/public/_headers").read_text(encoding="utf-8")

    assert "https://bibliografia-spravodaj.pages.dev/*" in headers
    assert "X-Robots-Tag: noindex" in headers
