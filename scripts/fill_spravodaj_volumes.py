#!/usr/bin/env python3
"""Fill missing Spravodaj SSS volume values from cached PDFs and year rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
DEFAULT_FRONTEND_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
DEFAULT_CAVES_PATH = BASE_DIR / "web" / "src" / "data" / "caves.json"
PDF_CACHE_DIR = BASE_DIR / "data" / "pdf_cache"
DEFAULT_JOURNAL_ID = "spravodaj_sss"

ROMAN_VALUES: tuple[tuple[int, str], ...] = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)
ROMAN_TO_INT = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def is_missing_volume(value: Any) -> bool:
    return str(value or "").strip() in {"", "-", "None"}


def article_journal_id(article: dict[str, Any]) -> str:
    return str(article.get("journal_id") or DEFAULT_JOURNAL_ID)


def to_roman(value: int) -> str:
    if value <= 0:
        raise ValueError(f"Roman volume must be positive, got {value}")
    rest = value
    parts: list[str] = []
    for number, roman in ROMAN_VALUES:
        while rest >= number:
            parts.append(roman)
            rest -= number
    return "".join(parts)


def roman_to_int(value: str) -> int | None:
    text = re.sub(r"[^IVXLCDM]", "", value.upper())
    if not text:
        return None
    total = 0
    previous = 0
    for char in reversed(text):
        current = ROMAN_TO_INT.get(char)
        if current is None:
            return None
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total


def spravodaj_volume_for_year(year: int) -> str:
    return f"{to_roman(year - 1969)}."


def safe_cache_name(url: str) -> str:
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "issue.pdf"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{stem}"


def pdf_cache_path(url: str) -> Path | None:
    if not url:
        return None
    path = PDF_CACHE_DIR / safe_cache_name(url)
    return path if path.exists() else None


def extract_first_pages(pdf_path: Path, pages: int) -> str:
    result = subprocess.run(
        ["pdftotext", "-f", "1", "-l", str(pages), str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


def extract_volume_from_text(text: str) -> str | None:
    patterns = (
        r"\bročník\s+([IVXLCDM]{1,12})\b",
        r"\brocnik\s+([IVXLCDM]{1,12})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            roman = match.group(1).upper()
            if roman_to_int(roman):
                return f"{roman}."
    return None


def is_special_bulletin(article: dict[str, Any], first_pages_text: str) -> bool:
    issue = str(article.get("issue") or "").lower()
    url = str(article.get("pdf_url") or "").lower()
    text = first_pages_text.lower()
    return (
        "kongres" in issue
        or "kongres" in url
        or "special edition" in text
        or "bulletin of the slovak speleological society" in text
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_articles(
    articles: list[dict[str, Any]],
    updates_by_id: dict[int, str],
) -> int:
    changed = 0
    for article in articles:
        try:
            article_id = int(article["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if article_id not in updates_by_id:
            continue
        if article_journal_id(article) != DEFAULT_JOURNAL_ID:
            continue
        if not is_missing_volume(article.get("volume")):
            continue
        article["volume"] = updates_by_id[article_id]
        changed += 1
    return changed


def update_cave_articles(caves: list[dict[str, Any]], updates_by_id: dict[int, str]) -> int:
    changed = 0
    for cave in caves:
        for article in cave.get("articles", []):
            try:
                article_id = int(article["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if article_id not in updates_by_id:
                continue
            if article_journal_id(article) != DEFAULT_JOURNAL_ID:
                continue
            if not is_missing_volume(article.get("volume")):
                continue
            article["volume"] = updates_by_id[article_id]
            changed += 1
    return changed


def existing_volume_map(articles: list[dict[str, Any]]) -> dict[int, str]:
    volumes: dict[int, str] = {}
    for article in articles:
        if article_journal_id(article) != DEFAULT_JOURNAL_ID:
            continue
        if is_missing_volume(article.get("volume")):
            continue
        try:
            article_id = int(article["id"])
        except (KeyError, TypeError, ValueError):
            continue
        volumes[article_id] = str(article.get("volume") or "").strip()
    return volumes


def collect_updates(
    articles: list[dict[str, Any]],
    *,
    first_pages: int,
    infer_regular_issues: bool,
) -> tuple[dict[int, str], list[dict[str, Any]]]:
    groups: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        if article_journal_id(article) != DEFAULT_JOURNAL_ID:
            continue
        if not is_missing_volume(article.get("volume")):
            continue
        year = article.get("year")
        if not isinstance(year, int):
            continue
        groups[(year, str(article.get("issue") or ""), str(article.get("pdf_url") or ""))].append(article)

    updates_by_id: dict[int, str] = {}
    issue_summaries: list[dict[str, Any]] = []
    text_cache: dict[str, str] = {}
    for (year, issue, pdf_url), issue_articles in sorted(groups.items()):
        cache_path = pdf_cache_path(pdf_url)
        first_pages_text = ""
        extracted_volume = None
        reason = "missing_pdf_cache"
        if cache_path:
            try:
                if pdf_url not in text_cache:
                    text_cache[pdf_url] = extract_first_pages(cache_path, first_pages)
                first_pages_text = text_cache[pdf_url]
                extracted_volume = extract_volume_from_text(first_pages_text)
                reason = "pdf_ročník_not_found"
            except (subprocess.SubprocessError, OSError) as exc:
                reason = f"pdf_text_failed:{exc.__class__.__name__}"

        volume = extracted_volume
        source = "pdf"
        if not volume and infer_regular_issues and not is_special_bulletin(issue_articles[0], first_pages_text):
            try:
                volume = spravodaj_volume_for_year(year)
                source = "year_rule"
            except ValueError:
                reason = "year_out_of_range"

        if volume:
            for article in issue_articles:
                updates_by_id[int(article["id"])] = volume
            reason = "filled"
        else:
            source = "skipped"

        issue_summaries.append(
            {
                "year": year,
                "issue": issue,
                "articles": len(issue_articles),
                "volume": volume or "",
                "source": source,
                "reason": reason,
                "pdf_cache": str(cache_path.relative_to(BASE_DIR)) if cache_path else "",
                "pdf_url": pdf_url,
            }
        )
    return updates_by_id, issue_summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--frontend-articles", type=Path, default=DEFAULT_FRONTEND_ARTICLES_PATH)
    parser.add_argument("--caves", type=Path, default=DEFAULT_CAVES_PATH)
    parser.add_argument("--first-pages", type=int, default=4)
    parser.add_argument("--no-infer-regular-issues", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    articles = load_json(args.articles)
    updates_by_id, issue_summaries = collect_updates(
        articles,
        first_pages=args.first_pages,
        infer_regular_issues=not args.no_infer_regular_issues,
    )

    source_counts = Counter(summary["source"] for summary in issue_summaries)
    volume_counts = Counter(summary["volume"] for summary in issue_summaries if summary["volume"])
    report = {
        "issues_seen": len(issue_summaries),
        "articles_to_update": len(updates_by_id),
        "issue_sources": dict(source_counts),
        "volumes": dict(sorted(volume_counts.items())),
        "skipped": [summary for summary in issue_summaries if not summary["volume"]],
    }

    if args.apply:
        canonical_changed = update_articles(articles, updates_by_id)
        if canonical_changed:
            write_json(args.articles, articles)
        sync_by_id = existing_volume_map(articles)

        frontend_articles = load_json(args.frontend_articles)
        frontend_changed = update_articles(frontend_articles, sync_by_id)
        if frontend_changed:
            write_json(args.frontend_articles, frontend_articles)

        caves = load_json(args.caves)
        caves_changed = update_cave_articles(caves, sync_by_id)
        if caves_changed:
            write_json(args.caves, caves)

        report.update(
            {
                "applied": True,
                "canonical_changed": canonical_changed,
                "frontend_changed": frontend_changed,
                "cave_article_changed": caves_changed,
                "sync_volume_ids": len(sync_by_id),
            }
        )
    else:
        report["applied"] = False

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
