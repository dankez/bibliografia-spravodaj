#!/usr/bin/env python3
"""Apply confirmed AI map/plan detections to article JSON files."""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLE_PATHS = [
    BASE_DIR / "data" / "articles_with_urls.json",
    BASE_DIR / "web" / "src" / "data" / "articles.json",
]
MAP_TAG = "mapa/plán"
DEFAULT_PATTERN = "data/ai_map_detection/map_confirmed_*_hybrid_ocr_minicpm46_2024plus.jsonl"


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
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc


def clear_map_fields(article: dict[str, Any]) -> None:
    article.pop("has_map_plan", None)
    article.pop("map_plan_score", None)
    article.pop("map_plan_pages", None)
    detected = article.get("detected_features")
    if isinstance(detected, dict):
        detected.pop("map_plan", None)
    tags = article.get("tags")
    if isinstance(tags, list):
        article["tags"] = [tag for tag in tags if str(tag).strip().casefold() != MAP_TAG]


def source_label(record: dict[str, Any]) -> str:
    sources = record.get("prefilter", {}).get("candidate_sources") or []
    if "ocr_object_without_caption" in sources:
        return "ocr_object_without_caption"
    if "caption_object" in sources:
        return "caption_object"
    return "unknown"


def record_in_scope(record: dict[str, Any], year_from: int, year: int | None, issue: str | None) -> bool:
    record_year = int(record.get("year") or 0)
    if year is not None and record_year != year:
        return False
    if year is None and record_year < year_from:
        return False
    if issue is not None and str(record.get("issue")) != str(issue):
        return False
    return True


def article_in_scope(article: dict[str, Any], year_from: int, year: int | None, issue: str | None) -> bool:
    try:
        article_year = int(article.get("year") or 0)
    except (TypeError, ValueError):
        return False
    if year is not None and article_year != year:
        return False
    if year is None and article_year < year_from:
        return False
    if issue is not None and str(article.get("issue")) != str(issue):
        return False
    return True


def load_hits(pattern: str, year_from: int, year_filter: int | None, issue_filter: str | None) -> dict[int, dict[str, Any]]:
    hits: dict[int, dict[str, Any]] = {}
    for filename in sorted(glob.glob(str(BASE_DIR / pattern))):
        path = Path(filename)
        for record in iter_jsonl(path):
            if record.get("ai", {}).get("map_plan") is not True:
                continue
            year = int(record.get("year") or 0)
            if not record_in_scope(record, year_from, year_filter, issue_filter):
                continue
            page = int(record["page"])
            source = source_label(record)
            for article in record.get("articles") or []:
                article_id = int(article["id"])
                hit = hits.setdefault(
                    article_id,
                    {
                        "pages": set(),
                        "sources": set(),
                        "evidence": [],
                        "records": [],
                    },
                )
                hit["pages"].add(page)
                hit["sources"].add(source)
                hit["evidence"].append(
                    f"{year}/{record.get('issue')} PDF strana {page}: {source}, "
                    f"{record.get('ai', {}).get('kind')} {record.get('ai', {}).get('confidence')}"
                )
                hit["records"].append(
                    {
                        "year": year,
                        "issue": str(record.get("issue")),
                        "page": page,
                        "source": source,
                        "kind": record.get("ai", {}).get("kind"),
                        "confidence": record.get("ai", {}).get("confidence"),
                    }
                )
    return hits


def apply_to_articles(
    path: Path,
    hits: dict[int, dict[str, Any]],
    year_from: int,
    year_filter: int | None,
    issue_filter: str | None,
    model_label: str,
    dry_run: bool,
) -> dict[str, int]:
    articles = read_json(path)
    cleared = 0
    applied = 0
    now = utc_now()
    for article in articles:
        if not isinstance(article, dict):
            continue
        try:
            article_id = int(article.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if article_in_scope(article, year_from, year_filter, issue_filter):
            clear_map_fields(article)
            cleared += 1
        hit = hits.get(article_id)
        if not hit:
            continue
        pages = sorted(int(page) for page in hit["pages"])
        sources = sorted(str(source) for source in hit["sources"])
        evidence = sorted(set(str(item) for item in hit["evidence"]))
        detected = article.setdefault("detected_features", {})
        detected["map_plan"] = {
            "present": True,
            "score": 0.99,
            "pages": pages,
            "evidence": evidence,
            "sources": sources,
            "model": model_label,
            "updated_at": now,
        }
        article["has_map_plan"] = True
        article["map_plan_score"] = 0.99
        article["map_plan_pages"] = pages
        tags = article.setdefault("tags", [])
        if MAP_TAG not in tags:
            tags.append(MAP_TAG)
        applied += 1
    if not dry_run:
        write_json(path, articles)
    return {"cleared_year_scope": cleared, "applied": applied}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default=DEFAULT_PATTERN)
    parser.add_argument("--year-from", type=int, default=2024)
    parser.add_argument("--year", type=int, help="Restrict records and clearing to one year.")
    parser.add_argument("--issue", help="Restrict records and clearing to one issue.")
    parser.add_argument("--model-label", default="minicpm-v4.6")
    parser.add_argument(
        "--summary-path",
        default="data/ai_map_detection/applied_hybrid_ocr_minicpm46_2024plus_summary.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hits = load_hits(args.pattern, args.year_from, args.year, args.issue)
    article_counts = {
        str(path.relative_to(BASE_DIR)): apply_to_articles(
            path,
            hits,
            args.year_from,
            args.year,
            args.issue,
            args.model_label,
            args.dry_run,
        )
        for path in ARTICLE_PATHS
    }
    summary = {
        "created_at": utc_now(),
        "pattern": args.pattern,
        "year_from": args.year_from,
        "year": args.year,
        "issue": args.issue,
        "model_label": args.model_label,
        "article_hit_count": len(hits),
        "article_counts": article_counts,
        "hits": {
            str(article_id): {
                "pages": sorted(int(page) for page in hit["pages"]),
                "sources": sorted(str(source) for source in hit["sources"]),
                "records": hit["records"],
            }
            for article_id, hit in sorted(hits.items())
        },
    }
    summary_path = BASE_DIR / args.summary_path
    if not args.dry_run:
        write_json(summary_path, summary)
    print(json.dumps(summary | {"summary_path": str(summary_path.relative_to(BASE_DIR))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
