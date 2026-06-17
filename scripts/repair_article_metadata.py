#!/usr/bin/env python3
"""Repair article year/issue metadata when the PDF filename is authoritative."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai_scrape_new_issues import parse_issue_from_filename


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FRONTEND_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"


def read_articles(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected a list in {path}")
    return data


def write_articles(path: Path, articles: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(articles, handle, ensure_ascii=False, indent=2)


def repair_articles(articles: list[dict]) -> list[dict]:
    changes: list[dict] = []
    for article in articles:
        pdf_url = str(article.get("pdf_url") or "")
        parsed = parse_issue_from_filename(pdf_url)
        if not parsed:
            continue

        year, issue = parsed
        old_year = article.get("year")
        old_issue = str(article.get("issue") or "")
        if old_year == year and old_issue == issue:
            continue

        article["year"] = year
        article["issue"] = issue
        changes.append(
            {
                "id": article.get("id"),
                "title": article.get("title", ""),
                "pdf_url": pdf_url,
                "old": {"year": old_year, "issue": old_issue},
                "new": {"year": year, "issue": issue},
            }
        )
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair Spravodaj article year/issue metadata from PDF filenames.")
    parser.add_argument("--articles", default=str(ARTICLES_PATH), help="Canonical articles JSON.")
    parser.add_argument("--frontend", default=str(FRONTEND_ARTICLES_PATH), help="Frontend articles JSON to sync.")
    parser.add_argument("--dry-run", action="store_true", help="Print repairs without writing files.")
    args = parser.parse_args()

    articles_path = Path(args.articles)
    frontend_path = Path(args.frontend)
    articles = read_articles(articles_path)
    changes = repair_articles(articles)

    print(json.dumps({"changed": len(changes), "changes": changes}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    write_articles(articles_path, articles)
    if frontend_path.parent.exists():
        write_articles(frontend_path, articles)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
