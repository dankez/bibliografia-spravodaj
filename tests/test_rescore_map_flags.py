import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rescore_map_flags as rescore


def test_plain_pl_in_extras_is_added():
    article = {"id": 1, "title": "Klátovský kras", "extras": ["1 obr.", "1 pl."], "has_map_plan": False, "tags": []}

    change = rescore.plan_change(article)
    assert change and change["action"] == "add"
    rescore.apply_change(article, change)

    assert article["has_map_plan"] is True
    assert "mapa/plán" in article["tags"]
    assert rescore.plan_change(article) is None


def test_text_only_activity_report_is_demoted_and_stays_demoted():
    article = {
        "id": 2,
        "title": "Správa o činnosti SSS za rok 1998",
        "extras": [],
        "has_map_plan": True,
        "map_plan_score": 1.0,
        "map_plan_pages": [16],
        "tags": ["mapa/plán"],
        "detected_features": {"map_plan": {"methods": ["text"], "evidence": ["text: mierka 1:n"]}},
    }

    change = rescore.plan_change(article)
    assert change and change["action"] == "demote"
    rescore.apply_change(article, change)

    assert article["has_map_plan"] is False
    assert article["map_plan_pages"] == []
    assert "mapa/plán" not in article["tags"]
    assert rescore.plan_change(article) is None


def test_report_with_metadata_evidence_is_kept():
    article = {
        "id": 3,
        "title": "Správa o činnosti oddielu",
        "extras": ["1 pl. j."],
        "has_map_plan": True,
        "map_plan_score": 0.98,
        "tags": ["mapa/plán"],
        "detected_features": {"map_plan": {"methods": ["metadata"], "evidence": []}},
    }

    assert rescore.plan_change(article) is None
