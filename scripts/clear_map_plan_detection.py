#!/usr/bin/env python3
"""Remove generated map/plan detection data from bibliography artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLE_PATHS = [
    BASE_DIR / "data" / "articles_with_urls.json",
    BASE_DIR / "web" / "src" / "data" / "articles.json",
]
FEATURES_PATH = BASE_DIR / "data" / "article_feature_detection.jsonl"
CANDIDATES_PATH = BASE_DIR / "data" / "map_plan_candidates.jsonl"
SUMMARY_PATH = BASE_DIR / "data" / "article_feature_detection_summary.json"
MAP_TAG = "mapa/plán"
MAP_KEYS = ("has_map_plan", "map_plan_score", "map_plan_pages")


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def clear_article(article: dict[str, Any]) -> bool:
    changed = False
    for key in MAP_KEYS:
        if key in article:
            article.pop(key, None)
            changed = True

    features = article.get("detected_features")
    if isinstance(features, dict) and "map_plan" in features:
        features.pop("map_plan", None)
        changed = True

    tags = article.get("tags")
    if isinstance(tags, list):
        cleaned = [tag for tag in tags if str(tag).strip().casefold() != MAP_TAG]
        if cleaned != tags:
            article["tags"] = cleaned
            changed = True

    return changed


def clear_article_files(paths: list[Path], dry_run: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        articles = read_json(path)
        changed = sum(1 for article in articles if isinstance(article, dict) and clear_article(article))
        counts[str(path.relative_to(BASE_DIR))] = changed
        if changed and not dry_run:
            write_json(path, articles)
    return counts


def clear_feature_jsonl(path: Path, dry_run: bool) -> int:
    if not path.exists():
        return 0
    rows = []
    changed = 0
    for row in iter_jsonl(path) or []:
        if clear_article(row):
            changed += 1
        features = row.get("features")
        if isinstance(features, dict) and "map_plan" in features:
            features.pop("map_plan", None)
            changed += 1
        rows.append(row)
    if changed and not dry_run:
        write_jsonl(path, rows)
    return changed


def clear_summary(path: Path, dry_run: bool) -> bool:
    if not path.exists():
        return False
    summary = read_json(path)
    if not isinstance(summary, dict):
        return False
    feature_counts = summary.setdefault("feature_counts", {})
    if isinstance(feature_counts, dict):
        feature_counts["map_plan"] = 0
    summary["map_plan_candidates"] = 0
    summary["map_plan_cleared_at"] = utc_now()
    summary["map_plan_clear_note"] = "Generated map/plan detection removed before AI-only PDF test."
    if not dry_run:
        write_json(path, summary)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    article_counts = clear_article_files(ARTICLE_PATHS, args.dry_run)
    feature_changes = clear_feature_jsonl(FEATURES_PATH, args.dry_run)
    if CANDIDATES_PATH.exists() and not args.dry_run:
        CANDIDATES_PATH.write_text("", encoding="utf-8")
    summary_changed = clear_summary(SUMMARY_PATH, args.dry_run)

    print("article_files=" + json.dumps(article_counts, ensure_ascii=False, sort_keys=True))
    print(f"feature_jsonl_changes={feature_changes}")
    print(f"map_plan_candidates_cleared={CANDIDATES_PATH.exists()}")
    print(f"summary_updated={summary_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
