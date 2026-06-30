import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import normalize_fulltext_cleanup as cleanup


def test_cleanup_text_removes_mechanical_artifacts():
    text = "jas-\nkyňa\u200b má   veľa   sintrov\r\nďalší\ttext\u0000"

    cleaned, stats = cleanup.cleanup_text(text)

    assert cleaned == "jaskyňa má veľa sintrov\nďalší\ttext"
    assert stats["hyphen_linebreaks"] == 1
    assert stats["hidden_chars"] == 2
    assert stats["multispace_runs"] == 2


def test_cleanup_text_keeps_normal_text_unchanged():
    text = "Jaskyňa má názov a krátky opis.\nDruhý riadok."

    cleaned, stats = cleanup.cleanup_text(text)

    assert cleaned == text
    assert all(value == 0 for value in stats.values())
