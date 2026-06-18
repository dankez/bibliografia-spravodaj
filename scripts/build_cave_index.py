#!/usr/bin/env python3
"""Build a compact cave/lokalita index for static web timeline pages."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "web" / "src" / "data" / "caves.json"
PDF_LINK_PAGE_OFFSET = 2


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: Any) -> str:
    return normalize_text(value).replace(" ", "-") or "jaskyna"


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        key = slugify(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def first_page(article: dict[str, Any]) -> int:
    value = article.get("pdf_page_start")
    if value in (None, ""):
        match = re.match(r"\s*(\d+)", str(article.get("pages") or ""))
        value = match.group(1) if match else 1
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def pdf_link(article: dict[str, Any]) -> str:
    url = str(article.get("pdf_url") or "").strip()
    if not url:
        return ""
    return f"{url}#page={first_page(article) + PDF_LINK_PAGE_OFFSET}"


def has_map_plan(article: dict[str, Any]) -> bool:
    return bool(
        article.get("has_map_plan")
        or article.get("map_plan_pages")
        or ((article.get("detected_features") or {}).get("map_plan") or {}).get("present")
    )


def cave_token_pattern(token: str) -> str:
    if token.startswith("jaskyn"):
        return r"jaskyn(?:a|e|i|u|ou|am|ami|ach|iach)?"
    if token.isdigit():
        return re.escape(token)
    if len(token) <= 3:
        return re.escape(token)
    if len(token) <= 5:
        return f"{re.escape(token)}[a-z0-9]*"
    return f"{re.escape(token[:-1])}[a-z0-9]*"


def cave_phrase_pattern(cave_name: str) -> re.Pattern[str] | None:
    tokens = normalize_text(cave_name).split()
    if not tokens:
        return None
    parts = [cave_token_pattern(token) for token in tokens]
    return re.compile(rf"\b{' '.join(parts).replace(' ', r' +')}\b")


def article_text_for_cave_match(article: dict[str, Any]) -> str:
    values = [
        article.get("title") or "",
        article.get("abstract") or "",
    ]
    return normalize_text(" ".join(values))


def article_mentions_cave(article: dict[str, Any], cave_name: str) -> bool:
    pattern = cave_phrase_pattern(cave_name)
    if pattern is None:
        return False
    return bool(pattern.search(article_text_for_cave_match(article)))


def article_summary(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(article["id"]),
        "title": article.get("title") or "",
        "year": article.get("year"),
        "issue": str(article.get("issue") or ""),
        "pages": str(article.get("pages") or ""),
        "authors": unique_strings(article.get("authors") or []),
        "abstract": article.get("abstract") or "",
        "has_map_plan": has_map_plan(article),
        "map_plan_pages": article.get("map_plan_pages") or [],
        "pdf_url": article.get("pdf_url") or "",
        "pdf_link": pdf_link(article),
        "detail_url": f"/clanky/{article['id']}/",
    }


def build_cave_index(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    slug_counts: defaultdict[str, int] = defaultdict(int)

    for article in articles:
        for cave_name in unique_strings(article.get("caves") or []):
            if not article_mentions_cave(article, cave_name):
                continue
            key = slugify(cave_name)
            if key not in grouped:
                slug_counts[key] += 1
                slug = key if slug_counts[key] == 1 else f"{key}-{slug_counts[key]}"
                grouped[key] = {"name": cave_name, "slug": slug, "articles": []}
            grouped[key]["articles"].append(article_summary(article))

    caves: list[dict[str, Any]] = []
    for cave in grouped.values():
        article_rows = sorted(
            cave["articles"],
            key=lambda item: (int(item.get("year") or 0), int(item.get("id") or 0)),
        )
        years = [int(item["year"]) for item in article_rows if item.get("year")]
        authors = {
            author
            for item in article_rows
            for author in item.get("authors", [])
            if author not in {"Anonymus", "Redakcia"}
        }
        caves.append(
            {
                "name": cave["name"],
                "slug": cave["slug"],
                "article_count": len(article_rows),
                "map_plan_count": sum(1 for item in article_rows if item.get("has_map_plan")),
                "first_year": min(years) if years else None,
                "last_year": max(years) if years else None,
                "authors_count": len(authors),
                "articles": article_rows,
            }
        )

    return sorted(
        caves,
        key=lambda item: (-int(item["article_count"]), str(item["name"]).casefold()),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    articles = json.loads(args.articles.read_text(encoding="utf-8"))
    caves = build_cave_index(articles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(caves, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "caves": len(caves)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
