import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import import_slovensky_kras_monographs as monographs


def test_monograph_manifest_lookup_uses_slovensky_kras_issue_keys():
    manifest = {
        "items": [
            {"journal_id": "slovensky_kras", "issue_key": "53_2015_1-2"},
            {"journal_id": "aragonit", "issue_key": "53_2015_1-2"},
        ]
    }

    assert monographs.manifest_items_by_issue_key(manifest) == {
        "53_2015_1-2": {"journal_id": "slovensky_kras", "issue_key": "53_2015_1-2"}
    }


def test_monograph_metadata_contains_expected_single_issue_records():
    assert monographs.MONOGRAPH_ARTICLES["53_2015_1-2"]["pages"] == "3-112"
    assert monographs.MONOGRAPH_ARTICLES["61_2023_suppl"]["pages"] == "2-62"
    assert monographs.source_issue_key("61_2023_suppl") == "slovensky_kras:61_2023_suppl"
