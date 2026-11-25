import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fix_spravodaj_metadata as fix


def test_roman_volume_rule_matches_known_years():
    assert fix.roman(2026 - 1969) == "LVII"
    assert fix.roman(1970 - 1969) == "I"
    assert fix.roman(2024 - 1969) == "LV"


def test_duplicate_keeps_lower_id_and_removes_identical_record():
    base = {"journal_id": "spravodaj_sss", "title": "Úvodník", "year": 1980, "issue": "2", "pdf_url": "", "pages": "3", "volume": "XI.", "authors": ["Redakcia"]}
    articles = [dict(base, id=404), dict(base, id=415)]

    report, remove = fix.fix_records(articles)

    assert remove == {415}
    assert report["duplicates"] == [(415, 404)]


def test_missing_volume_is_derived_and_marked():
    articles = [{"id": 7, "journal_id": "spravodaj_sss", "title": "X", "year": 2013, "issue": "1", "pages": "", "pdf_url": "", "volume": None}]

    report, remove = fix.fix_records(articles)
    updated = fix.apply(articles, report, remove)

    assert updated[0]["volume"] == roman_for(2013)
    assert updated[0]["volume_derived"] is True


def roman_for(year):
    return fix.roman(year - 1969)
