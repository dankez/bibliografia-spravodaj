#!/usr/bin/env python3
"""Opraví príznak mapa/plán v dátach bez nového čítania PDF.

Používa iba uložené metadáta a už zapísané `detected_features`:
- metadátový dôkaz mapy (`pl. j.`, `N pl.`, mapa/plán v prílohách), ktorý pôvodná detekcia minula, sa doplní,
- článok označený iba textovou detekciou, ktorý je správou/adresárom, sa zníži na kandidáta.

Predvolene iba vypíše zmeny; zápis vyžaduje `--apply`.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import detect_article_features as detector

MAP_TAG = detector.FEATURE_TAGS["map_plan"]


def current_methods(article: dict[str, Any]) -> list[str]:
    detected = (article.get("detected_features") or {}).get("map_plan") or {}
    return list(detected.get("methods") or [])


def plan_change(article: dict[str, Any]) -> dict[str, Any] | None:
    """Vráti nový stav map_plan alebo None, ak sa nič nemení."""
    threshold = detector.FEATURE_THRESHOLDS["map_plan"]
    metadata_map = detector.finalize_features(detector.score_metadata(article))["map_plan"]
    flagged = bool(article.get("has_map_plan"))

    if not flagged and metadata_map["present"]:
        return {
            "action": "add",
            "present": True,
            "score": metadata_map["score"],
            "confidence": metadata_map["confidence"],
            "pages": [],
            "evidence": metadata_map["evidence"],
            "methods": metadata_map["methods"],
        }

    text_only = "metadata" not in current_methods(article) and not metadata_map["present"]
    if flagged and text_only and detector.REPORT_TITLE_RE.match(detector.fold_text(article.get("title") or "")):
        old = (article.get("detected_features") or {}).get("map_plan") or {}
        return {
            "action": "demote",
            "present": False,
            "score": min(float(article.get("map_plan_score") or 0.0), threshold - 0.01),
            "confidence": "candidate",
            "pages": [],
            "evidence": list(old.get("evidence") or []) + ["guard: správa/adresár bez metadátového dôkazu"],
            "methods": list(old.get("methods") or []),
        }
    return None


def apply_change(article: dict[str, Any], change: dict[str, Any]) -> None:
    present = bool(change["present"])
    article["has_map_plan"] = present
    article["map_plan_score"] = change["score"]
    article["map_plan_pages"] = list(change["pages"])
    tags = [tag for tag in article.get("tags") or [] if tag != MAP_TAG]
    article["tags"] = tags + [MAP_TAG] if present else tags
    if "detected_features" in article:
        entry = dict(article["detected_features"].get("map_plan") or {})
        entry.update(
            present=present,
            score=change["score"],
            confidence=change["confidence"],
            pages=list(change["pages"]),
            evidence=detector.unique(change["evidence"])[:18],
            methods=change["methods"],
            updated_at=detector.utc_now(),
        )
        article["detected_features"]["map_plan"] = entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="zapísať zmeny do dát")
    args = parser.parse_args()

    articles = detector.read_json(detector.ARTICLES_PATH)
    changes: dict[int, dict[str, Any]] = {}
    for article in articles:
        change = plan_change(article)
        if change:
            changes[article["id"]] = change
            print(f"{change['action']:6} {article['id']:>5} {article.get('year')} {article.get('title', '')[:70]}")
    print(f"zmien: {len(changes)}")
    if not args.apply or not changes:
        return 0

    for article in articles:
        if article["id"] in changes:
            apply_change(article, changes[article["id"]])
    detector.write_json(detector.ARTICLES_PATH, articles)

    web_articles = detector.read_json(detector.WEB_ARTICLES_PATH)
    for article in web_articles:
        if article["id"] in changes:
            apply_change(article, changes[article["id"]])
    detector.write_json(detector.WEB_ARTICLES_PATH, web_articles)

    rows = list(detector.iter_jsonl(detector.OUTPUT_PATH) or [])
    for row in rows:
        change = changes.get(row.get("id"))
        if not change:
            continue
        feature = row["features"]["map_plan"]
        feature.update(
            present=change["present"], score=change["score"], confidence=change["confidence"],
            pages=list(change["pages"]), evidence=detector.unique(change["evidence"])[:18], methods=change["methods"],
        )
        row.update(has_map_plan=change["present"], map_plan_score=change["score"], map_plan_pages=list(change["pages"]))
    detector.write_jsonl(detector.OUTPUT_PATH, rows)

    summary = detector.read_json(detector.SUMMARY_PATH)
    summary["feature_counts"]["map_plan"] = sum(1 for article in articles if article.get("has_map_plan"))
    detector.write_json(detector.SUMMARY_PATH, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
