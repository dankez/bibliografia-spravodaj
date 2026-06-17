import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import detect_article_features as detector


def test_metadata_pl_j_marks_article_as_map_plan():
    article = {
        "id": 17,
        "title": "Z činnosti oblastnej skupiny",
        "extras": ["1 pl. j."],
        "tags": [],
    }

    result = detector.detect_article(article, None)

    assert result["has_map_plan"] is True
    assert result["features"]["map_plan"]["confidence"] == "high"
    assert "metadata: pl. j." in result["features"]["map_plan"]["evidence"]


def test_plan_of_work_is_not_classified_as_map_plan():
    article = {
        "id": 1,
        "title": "Plán práce oblastnej skupiny",
        "extras": [],
        "tags": [],
    }
    record = {
        "id": 1,
        "pdf_page_start": 10,
        "text": "Plán práce skupiny na rok 1987. Program schôdze a plán činnosti členov.",
    }

    result = detector.detect_article(article, record)

    assert result["has_map_plan"] is False
    assert result["features"]["map_plan"]["score"] < detector.FEATURE_THRESHOLDS["map_plan"]


def test_scale_floor_plan_and_survey_terms_mark_map_plan_page():
    article = {"id": 2, "title": "Nová jaskyňa", "extras": [], "tags": []}
    record = {
        "id": 2,
        "pdf_page_start": 42,
        "text": "Pôdorys jaskyne, mierka 1:500. Merali a kreslili členovia skupiny, legenda a polygón.",
    }

    result = detector.detect_article(article, record)

    assert result["has_map_plan"] is True
    assert result["map_plan_pages"] == [42]
    assert result["features"]["map_plan"]["score"] >= 0.65


def test_scale_and_generic_map_word_is_only_candidate():
    article = {"id": 3, "title": "Správa skupiny", "extras": [], "tags": []}
    record = {
        "id": 3,
        "pdf_page_start": 12,
        "text": "V texte sa spomína mapa regiónu a mierka 1:50000 bez plánu jaskyne alebo meračskej dokumentácie.",
    }

    result = detector.detect_article(article, record)

    assert result["has_map_plan"] is False
    assert result["features"]["map_plan"]["confidence"] == "candidate"


def test_explicit_map_attachment_in_metadata_is_map_plan():
    article = {
        "id": 4,
        "title": "Krasové územie",
        "extras": ["1 mapa"],
        "tags": [],
    }

    result = detector.detect_article(article, None)

    assert result["has_map_plan"] is True
    assert result["features"]["map_plan"]["score"] >= detector.FEATURE_THRESHOLDS["map_plan"]


def test_update_articles_adds_detected_tags_idempotently():
    article = {"id": 2, "tags": ["Speleológia"]}
    result = {
        "id": 2,
        "features": detector.finalize_features(
            {
                **detector.empty_features(),
                "map_plan": {
                    "present": True,
                    "score": 0.9,
                    "confidence": "high",
                    "pages": [42],
                    "evidence": ["metadata: pl. j."],
                    "methods": ["metadata"],
                },
            }
        ),
    }

    updated = detector.update_articles_with_results([article], {2: result})
    detector.update_articles_with_results([article], {2: result})

    assert updated == 1
    assert article["has_map_plan"] is True
    assert article["tags"].count("mapa/plán") == 1
    assert article["detected_features"]["map_plan"]["pages"] == [42]
