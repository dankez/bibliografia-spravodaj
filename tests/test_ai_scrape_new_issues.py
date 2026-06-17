import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ai_scrape_new_issues as scraper


def test_parse_link_info_prefers_filename_year_over_upload_folder():
    info = scraper.parse_link_info(
        "Spravodaj",
        "https://sss.sk/wp-content/uploads/2026/01/Spravodaj_3_2025_web.pdf",
    )

    assert info["year"] == 2025
    assert info["issue"] == "3"
    assert info["key"] == "2025_3"


def test_parse_link_info_detects_kongres_year_from_filename():
    info = scraper.parse_link_info(
        "Kongres",
        "https://sss.sk/wp-content/uploads/2021/05/Spravodaj_2013_kongres.pdf",
    )

    assert info["year"] == 2013
    assert info["issue"] == "kongres"
    assert info["key"] == "2013_kongres"


def test_parse_link_info_uses_url_map_key_for_short_numeric_pdf_name():
    info = scraper.parse_link_info(
        "Spravodaj",
        "https://sss.sk/wp-content/uploads/2017/10/174.pdf",
        issue_key="2017_4",
    )

    assert info["year"] == 2017
    assert info["issue"] == "4"
    assert info["key"] == "2017_4"


def test_parse_link_info_preserves_combined_issue_from_filename():
    info = scraper.parse_link_info(
        "Spravodaj SSS",
        "https://sss.sk/wp-content/uploads/2022/03/Spravodaj_SSS_1-2_1985.pdf",
    )

    assert info["year"] == 1985
    assert info["issue"] == "1-2"
    assert info["key"] == "1985_1-2"


def test_missing_issue_infos_from_url_map_skips_existing_keys():
    url_map = {
        "2009_4": "https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2009-4.pdf",
        "2010_1": "https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2010-1.pdf",
        "2025_3": "https://sss.sk/wp-content/uploads/2026/01/Spravodaj_3_2025_web.pdf",
    }
    existing = [
        {"year": 2009, "issue": "4"},
        {"year": 2025, "issue": "3"},
    ]

    missing = scraper.missing_issue_infos_from_url_map(url_map, existing)

    assert [item["key"] for item in missing] == ["2010_1"]
    assert missing[0]["year"] == 2010
    assert missing[0]["issue"] == "1"
