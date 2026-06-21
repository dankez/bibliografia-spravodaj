#!/usr/bin/env python3
"""Import Slovensky kras monothematic issues that do not have a classic TOC."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import import_journal_issues as journal_import


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = BASE_DIR / "data" / "journal_sources_manifest.json"
DEFAULT_ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
DEFAULT_FRONTEND_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
CREATED_BY = "manual_monograph_import"
MODEL = "manual_monograph_metadata"

MONOGRAPH_ARTICLES: dict[str, dict[str, Any]] = {
    "53_2015_1-2": {
        "title": "Súpis jaskýň na Zádielskej planine v Slovenskom krase",
        "authors": ["Kladiva, E.", "Terray, M.", "Lešinský, G."],
        "pages": "3-112",
        "extras": [],
        "abstract": (
            "Inventarizačný súpis jaskýň Zádielskej planiny s históriou prieskumu, "
            "názvoslovím, lokalizáciou a základnou charakteristikou známych lokalít."
        ),
        "caves": [],
        "has_map_plan": False,
    },
    "61_2023_suppl": {
        "title": "Inventarizačný prieskum jaskýň doliny Malý Ružinok",
        "authors": ["Miškov, M.", "Psotka, J."],
        "pages": "2-62",
        "extras": [],
        "abstract": (
            "Inventarizačný prehľad jaskýň doliny Malý Ružinok a krasu Sivca "
            "so základnou charakteristikou územia a zdokumentovaných lokalít."
        ),
        "caves": [],
        "has_map_plan": False,
    },
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_issue_key(issue_key: str) -> str:
    return f"slovensky_kras:{issue_key}"


def manifest_items_by_issue_key(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("issue_key")): item
        for item in manifest.get("items") or []
        if item.get("journal_id") == "slovensky_kras"
    }


def build_records(
    *,
    manifest: dict[str, Any],
    existing_articles: list[dict[str, Any]],
    issue_keys: list[str],
    created_at: str,
) -> list[dict[str, Any]]:
    items = manifest_items_by_issue_key(manifest)
    existing_keys = journal_import.existing_source_issue_keys(existing_articles)
    next_id = max((int(article.get("id") or 0) for article in existing_articles), default=0) + 1
    records: list[dict[str, Any]] = []

    for issue_key in issue_keys:
        key = source_issue_key(issue_key)
        if key in existing_keys:
            continue
        item = items[issue_key]
        pdf_path = journal_import.download_issue_pdf(item)
        page_map = journal_import.infer_printed_to_physical_page_map(
            pdf_path,
            journal_import.fulltext.TEXT_CACHE_DIR
            / f"{journal_import.fulltext.safe_name(str(item.get('pdf_url')))}.journal-pages.json",
        )
        built = journal_import.build_article_records(
            item,
            [MONOGRAPH_ARTICLES[issue_key]],
            start_id=next_id,
            printed_to_physical=page_map,
            created_at=created_at,
            model=MODEL,
        )
        for article in built:
            article["created_by"] = CREATED_BY
            article["abstract_source"] = "manual_monograph"
            article["abstract_generated_by"] = MODEL
        records.extend(built)
        next_id += len(built)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--frontend", type=Path, default=DEFAULT_FRONTEND_PATH)
    parser.add_argument("--issue-key", action="append", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = read_json(args.manifest)
    articles = read_json(args.articles)
    issue_keys = args.issue_key or list(MONOGRAPH_ARTICLES)
    missing = [key for key in issue_keys if key not in MONOGRAPH_ARTICLES]
    if missing:
        raise SystemExit(f"Unknown monograph issue keys: {', '.join(missing)}")

    records = build_records(
        manifest=manifest,
        existing_articles=articles,
        issue_keys=issue_keys,
        created_at=utc_now(),
    )
    print(json.dumps({"selected": issue_keys, "new_records": len(records)}, ensure_ascii=False))
    if args.dry_run:
        for record in records:
            print(f"{record['source_issue_key']} {record['pages']} {record['title']}")
        return 0

    if records:
        articles.extend(records)
        write_json(args.articles, articles)
        write_json(args.frontend, articles)
    return 0


if __name__ == "__main__":
    sys.exit(main())
