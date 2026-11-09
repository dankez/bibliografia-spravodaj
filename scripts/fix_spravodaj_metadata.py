#!/usr/bin/env python3
"""Opravy metadát Spravodaja SSS (audit 2026-11-09). Predvolene suchý beh; zápis cez --apply.

Pravidlá:
- ročník (volume) chýbajúci: odvodí sa z roku (1970 = I., rok - 1969), označí sa volume_derived.
- duplicitný záznam (rovnaký názov, rok, číslo, PDF a strany): ponechá sa nižšie ID.
- chýbajúci pdf_page_start, keď sú strany a PDF v rozsahu: pdf_page_start = prvá tlačená strana + offset 2.
  Ostatné prípady (strany mimo PDF, bez strán) sa len vypíšu na ručnú kontrolu.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "scripts"))
import extract_pdf_fulltext as fulltext  # noqa: E402

ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FRONTEND_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
JOURNAL_ID = "spravodaj_sss"
PDF_OFFSET = 2
ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman(number: int) -> str:
    out = ""
    for value, symbol in ROMAN:
        while number >= value:
            out += symbol
            number -= value
    return out


def first_printed_page(pages: str | None) -> int | None:
    digits = "".join(ch if ch.isdigit() else " " for ch in str(pages or "")).split()
    return int(digits[0]) if digits else None


def pdf_page_count(pdf_url: str) -> int | None:
    path = BASE_DIR / "data" / "pdf_cache" / fulltext.safe_name(pdf_url)
    if not path.exists():
        return None
    return len(PdfReader(str(path)).pages)


def fix_records(articles: list[dict[str, Any]]) -> tuple[dict[str, list[Any]], set[int]]:
    report: dict[str, list[Any]] = {"volume": [], "duplicates": [], "page_start": [], "manual": []}
    remove: set[int] = set()
    spravodaj = [a for a in articles if a.get("journal_id", JOURNAL_ID) == JOURNAL_ID]

    seen: dict[tuple[Any, ...], int] = {}
    for article in sorted(spravodaj, key=lambda a: a["id"]):
        key = (str(article.get("title", "")).strip().lower(), article.get("year"), str(article.get("issue")), article.get("pdf_url"), str(article.get("pages")))
        if key in seen:
            remove.add(article["id"])
            report["duplicates"].append((article["id"], seen[key]))
        else:
            seen[key] = article["id"]

    for article in spravodaj:
        if article["id"] in remove:
            continue
        if not article.get("volume") and isinstance(article.get("year"), int):
            report["volume"].append((article["id"], article["year"], roman(article["year"] - 1969)))
        if article.get("pdf_url") and not article.get("pdf_page_start"):
            printed = first_printed_page(article.get("pages"))
            count = pdf_page_count(article["pdf_url"])
            last = first_printed_page(str(article.get("pages") or "").split("-")[-1])
            if printed and count and printed + PDF_OFFSET <= count and (last or printed) + PDF_OFFSET <= count:
                report["page_start"].append((article["id"], printed + PDF_OFFSET, (last or printed) + PDF_OFFSET))
            else:
                report["manual"].append((article["id"], article.get("year"), article.get("issue"), article.get("pages"), count))
        if not article.get("pages"):
            report["manual"].append((article["id"], article.get("year"), article.get("issue"), "bez strán", None))
    return report, remove


def apply(articles: list[dict[str, Any]], report: dict[str, list[Any]], remove: set[int]) -> list[dict[str, Any]]:
    volume = {item[0]: item[2] for item in report["volume"]}
    page_start = {item[0]: (item[1], item[2]) for item in report["page_start"]}
    out: list[dict[str, Any]] = []
    for article in articles:
        if article["id"] in remove:
            continue
        if article["id"] in volume:
            article["volume"] = volume[article["id"]]
            article["volume_derived"] = True
        if article["id"] in page_start:
            start, end = page_start[article["id"]]
            article["pdf_page_start"], article["pdf_page_end"] = start, end
            article["pdf_page_offset"] = PDF_OFFSET
        out.append(article)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    articles = json.loads(ARTICLES_PATH.read_text(encoding="utf-8"))
    report, remove = fix_records(articles)
    print(f"ročníky doplnené: {len(report['volume'])}")
    print(f"duplicity odstránené: {report['duplicates']}")
    print(f"pdf_page_start doplnené: {len(report['page_start'])}")
    print("na ručnú kontrolu:")
    for item in report["manual"]:
        print("  ", item)
    if not args.apply:
        print("suchý beh, zápis nebol vykonaný")
        return 0

    new_articles = apply(articles, report, remove)
    ARTICLES_PATH.write_text(json.dumps(new_articles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    frontend = json.loads(FRONTEND_PATH.read_text(encoding="utf-8"))
    FRONTEND_PATH.write_text(json.dumps(apply(frontend, report, remove), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"zapísané: {len(new_articles)} článkov")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
