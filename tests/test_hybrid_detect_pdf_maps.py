import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hybrid_detect_pdf_maps as hybrid


def test_reusable_page_record_rejects_empty_image(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"")

    problem = hybrid.reusable_page_record_problem({"page": 19, "image_path": str(image)})

    assert problem == "empty_image_file"


def test_reusable_page_record_accepts_nonempty_image(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"png")

    problem = hybrid.reusable_page_record_problem({"page": 19, "image_path": str(image)})

    assert problem is None


def test_reusable_records_by_page_filters_invalid_records(tmp_path):
    good = tmp_path / "good.png"
    bad = tmp_path / "bad.png"
    good.write_bytes(b"png")
    bad.write_bytes(b"")

    by_page, invalid = hybrid.reusable_records_by_page(
        [
            {"page": 18, "image_path": str(good)},
            {"page": 19, "image_path": str(bad)},
        ]
    )

    assert sorted(by_page) == [18]
    assert invalid == [{"page": 19, "reason": "empty_image_file"}]


def test_resolve_pdf_path_from_url_downloads_to_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(hybrid, "PDF_CACHE_DIR", tmp_path)

    def fake_download_pdf(url, target, force=False):
        target.write_bytes(b"%PDF")
        return True

    monkeypatch.setattr(hybrid, "download_pdf", fake_download_pdf)

    path, url = hybrid.resolve_pdf_path_from_url("https://sss.sk/wp-content/uploads/2017/10/b17.pdf")

    assert path == tmp_path / "efd8af406b_b17.pdf"
    assert path.read_bytes() == b"%PDF"
    assert url == "https://sss.sk/wp-content/uploads/2017/10/b17.pdf"
