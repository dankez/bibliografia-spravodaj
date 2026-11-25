#!/usr/bin/env python3
"""Build per-issue PDF page offsets from the printed page numbers in each PDF."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from extract_pdf_fulltext import (
    ARTICLES_PATH,
    PDF_CACHE_DIR,
    infer_issue_pdf_page_offset,
    infer_printed_page_map,
    parse_page_range,
    safe_name,
)
from pdf_page_links import DEFAULT_PDF_PAGE_OFFSET


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = BASE_DIR / "web" / "src" / "data" / "pdf_page_offsets.json"


def build_offsets(articles: list[dict]) -> tuple[dict[str, int], list[str]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for article in articles:
        journal_id = str(article.get("journal_id") or "spravodaj_sss")
        pdf_url = str(article.get("pdf_url") or "").strip()
        if journal_id == "spravodaj_sss" and pdf_url:
            grouped[pdf_url].append(article)

    offsets: dict[str, int] = {}
    fallbacks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="spravodaj-page-maps-") as temp_dir:
        cache_dir = Path(temp_dir)
        for pdf_url, issue_articles in sorted(grouped.items()):
            pdf_path = PDF_CACHE_DIR / safe_name(pdf_url)
            if not pdf_path.is_file():
                raise FileNotFoundError(f"Cached issue PDF is missing: {pdf_path}")

            page_map = infer_printed_page_map(
                pdf_path,
                cache_dir / f"{safe_name(pdf_url)}.pages.json",
                force=True,
            )
            offset = infer_issue_pdf_page_offset(issue_articles, page_map)
            if offset is None:
                metadata_offsets = []
                for article in issue_articles:
                    printed_start, _ = parse_page_range(article.get("pages", ""))
                    try:
                        physical_start = int(article.get("pdf_page_start"))
                    except (TypeError, ValueError):
                        continue
                    if printed_start is not None:
                        difference = physical_start - printed_start
                        if 0 < difference <= 6:
                            metadata_offsets.append(difference)
                if metadata_offsets:
                    counts = Counter(metadata_offsets)
                    highest_count = max(counts.values())
                    offset = next(value for value in metadata_offsets if counts[value] == highest_count)
                else:
                    offset = DEFAULT_PDF_PAGE_OFFSET
                fallbacks.append(pdf_url)
            offsets[pdf_url.split("#", 1)[0].split("?", 1)[0]] = offset

            candidates = [
                physical_page - printed_page
                for printed_page, physical_page in page_map.items()
                if 0 <= physical_page - printed_page <= 12
            ]
            distribution = Counter(candidates)
            if len(distribution) > 1 and offset != distribution.most_common(1)[0][0]:
                print(
                    f"First-page offset {offset} differs from page-map mode "
                    f"{dict(sorted(distribution.items()))}: {pdf_url}",
                    file=sys.stderr,
                )

    return dict(sorted(offsets.items())), fallbacks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=ARTICLES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    with args.articles.open("r", encoding="utf-8") as handle:
        articles = json.load(handle)

    offsets, fallbacks = build_offsets(articles)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(offsets, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(
        f"Wrote {len(offsets)} issue offsets to {args.output}; "
        f"{len(fallbacks)} used metadata/default fallback."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
