"""Resolve PDF page links from printed article pages and per-issue offsets."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
PDF_PAGE_OFFSETS_PATH = BASE_DIR / "web" / "src" / "data" / "pdf_page_offsets.json"
DEFAULT_JOURNAL_ID = "spravodaj_sss"
DEFAULT_PDF_PAGE_OFFSET = 2


def normalized_pdf_url(value: Any) -> str:
    return str(value or "").strip().split("#", 1)[0].split("?", 1)[0]


@lru_cache(maxsize=1)
def load_pdf_page_offsets() -> dict[str, int]:
    with PDF_PAGE_OFFSETS_PATH.open("r", encoding="utf-8") as handle:
        return {
            normalized_pdf_url(url): int(offset)
            for url, offset in json.load(handle).items()
        }


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def printed_page_start(article: dict[str, Any]) -> int | None:
    match = re.match(r"\s*(\d+)", str(article.get("pages") or ""))
    return int(match.group(1)) if match else None


def pdf_page_offset(
    article: dict[str, Any],
    fallback_offset: int = DEFAULT_PDF_PAGE_OFFSET,
) -> int:
    journal_id = str(article.get("journal_id") or DEFAULT_JOURNAL_ID)
    fallback = fallback_offset
    explicit = article.get("pdf_page_offset")
    if explicit not in (None, ""):
        offset = int_or_none(explicit)
        return offset if offset is not None else fallback
    if journal_id == DEFAULT_JOURNAL_ID:
        return load_pdf_page_offsets().get(normalized_pdf_url(article.get("pdf_url")), fallback)
    return fallback


def linked_pdf_page(article: dict[str, Any]) -> int | None:
    journal_id = str(article.get("journal_id") or DEFAULT_JOURNAL_ID)
    physical_start = int_or_none(article.get("pdf_page_start"))
    explicit_offset = int_or_none(article.get("pdf_page_offset"))
    printed_start = printed_page_start(article)
    if journal_id == DEFAULT_JOURNAL_ID:
        if physical_start is not None and explicit_offset is not None:
            return physical_start + explicit_offset
        if printed_start is None:
            return physical_start
        return printed_start + pdf_page_offset(article)

    start = physical_start or printed_start
    return start + pdf_page_offset(article) if start is not None else None
