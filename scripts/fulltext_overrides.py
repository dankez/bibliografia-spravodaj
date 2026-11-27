"""Load manually verified fulltexts and match them to their original PDF."""

import json
from pathlib import Path
from typing import Any

from pdf_page_links import normalized_pdf_url


OVERRIDES_PATH = Path(__file__).resolve().parents[1] / "data" / "fulltext_overrides.json"


def load_fulltext_overrides() -> dict[int, dict[str, Any]]:
    with OVERRIDES_PATH.open(encoding="utf-8") as handle:
        return {int(article_id): value for article_id, value in json.load(handle).items()}


def matches_override(record: dict[str, Any], override: dict[str, Any]) -> bool:
    return (
        str(record.get("journal_id") or "spravodaj_sss") == override["journal_id"]
        and str(record.get("year")) == str(override["year"])
        and bool(record.get("pdf_url"))
        and normalized_pdf_url(record["pdf_url"]) == normalized_pdf_url(override["pdf_url"])
    )


def apply_override(record: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    return {
        **record,
        "text": override["text"],
        "pdf_page_start": override["pdf_page_start"],
        "pdf_page_end": override["pdf_page_end"],
        "status": "ok",
        "text_source": "curated",
        "text_quality": None,
        "_curated_override": True,
    }
