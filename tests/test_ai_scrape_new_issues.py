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


def test_parse_link_info_detects_special_issue_links_without_standard_issue_number():
    cases = [
        (
            "Spravodaj-bibliografia",
            "https://sss.sk/wp-content/uploads/2020/02/Spravodaj-bibliografia.pdf",
            2011,
            "bibliografia",
        ),
        (
            "Bulletin of the Slovak Speleological Society",
            "https://sss.sk/wp-content/uploads/2017/10/b17.pdf",
            2017,
            "bulletin",
        ),
        (
            "Spravodaj 2022 kongres",
            "https://sss.sk/wp-content/uploads/2022/08/Spravodaj_2022_kongres_web.pdf",
            2022,
            "kongres",
        ),
    ]

    for link_text, url, year, issue in cases:
        info = scraper.parse_link_info(link_text, url)
        assert info["year"] == year
        assert info["issue"] == issue
        assert info["key"] == f"{year}_{issue}"


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


def test_parse_link_info_detects_1987_1992_alternate_periodical_names_from_site():
    cases = [
        ("Spravodaj 1987 1-2", "https://sss.sk/wp-content/uploads/2022/04/Spravodaj_SSS_1987_1-2.pdf", 1987, "1-2"),
        ("Spravodaj 1988-1-2", "https://sss.sk/wp-content/uploads/2022/05/Spravodaj_SSS_1-2_1988.pdf", 1988, "1-2"),
        ("Spravodaj 1989-1", "https://sss.sk/wp-content/uploads/2022/09/Spravodaj_SSS_1989_1.pdf", 1989, "1"),
        ("Spravodaj 1989-2", "https://sss.sk/wp-content/uploads/2022/09/Spravodaj_SSS_1989_2.pdf", 1989, "2"),
        ("Spravodajca 1990-1", "https://sss.sk/wp-content/uploads/2022/09/Spravodajca_SSS_1990_1.pdf", 1990, "1"),
        ("Jaskyniar 1991", "https://sss.sk/wp-content/uploads/2022/10/Jaskyniar_SSS_1991.pdf", 1991, "1"),
        ("Spravodajca 1992-1", "https://sss.sk/wp-content/uploads/2023/01/sp921.pdf", 1992, "1"),
        ("Spravodajca 1992-2", "https://sss.sk/wp-content/uploads/2023/01/sp922.pdf", 1992, "2"),
    ]

    for link_text, url, year, issue in cases:
        info = scraper.parse_link_info(link_text, url)
        assert info["year"] == year
        assert info["issue"] == issue
        assert info["key"] == f"{year}_{issue}"


def test_parse_link_info_detects_short_1992_sp_filename_without_link_text_year():
    first = scraper.parse_link_info("Spravodajca", "https://sss.sk/wp-content/uploads/2023/01/sp921.pdf")
    second = scraper.parse_link_info("Spravodajca", "https://sss.sk/wp-content/uploads/2023/01/sp922.pdf")

    assert first["key"] == "1992_1"
    assert second["key"] == "1992_2"


def test_parse_link_info_treats_annual_jaskyniar_1991_as_issue_one_without_link_text_year():
    info = scraper.parse_link_info("Jaskyniar", "https://sss.sk/wp-content/uploads/2022/10/Jaskyniar_SSS_1991.pdf")

    assert info["year"] == 1991
    assert info["issue"] == "1"
    assert info["key"] == "1991_1"


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


def test_missing_issue_infos_from_url_map_includes_legacy_1987_1992_pdf_keys():
    url_map = {
        "1987_1-2": "https://sss.sk/wp-content/uploads/2022/04/Spravodaj_SSS_1987_1-2.pdf",
        "1988_1-2": "https://sss.sk/wp-content/uploads/2022/05/Spravodaj_SSS_1-2_1988.pdf",
        "1989_1": "https://sss.sk/wp-content/uploads/2022/09/Spravodaj_SSS_1989_1.pdf",
        "1989_2": "https://sss.sk/wp-content/uploads/2022/09/Spravodaj_SSS_1989_2.pdf",
        "1990_1": "https://sss.sk/wp-content/uploads/2022/09/Spravodajca_SSS_1990_1.pdf",
        "1991_1": "https://sss.sk/wp-content/uploads/2022/10/Jaskyniar_SSS_1991.pdf",
        "1992_1": "https://sss.sk/wp-content/uploads/2023/01/sp921.pdf",
        "1992_2": "https://sss.sk/wp-content/uploads/2023/01/sp922.pdf",
    }

    missing = scraper.missing_issue_infos_from_url_map(url_map, existing_articles=[])

    assert [item["key"] for item in missing] == [
        "1987_1-2",
        "1988_1-2",
        "1989_1",
        "1989_2",
        "1990_1",
        "1991_1",
        "1992_1",
        "1992_2",
    ]


def test_missing_issue_infos_from_url_map_includes_special_issue_keys_without_standard_number():
    url_map = {
        "2011_bibliografia": "https://sss.sk/wp-content/uploads/2020/02/Spravodaj-bibliografia.pdf",
        "2017_bulletin": "https://sss.sk/wp-content/uploads/2017/10/b17.pdf",
        "2022_kongres": "https://sss.sk/wp-content/uploads/2022/08/Spravodaj_2022_kongres_web.pdf",
    }

    missing = scraper.missing_issue_infos_from_url_map(url_map, existing_articles=[])

    assert [item["key"] for item in missing] == [
        "2011_bibliografia",
        "2017_bulletin",
        "2022_kongres",
    ]
