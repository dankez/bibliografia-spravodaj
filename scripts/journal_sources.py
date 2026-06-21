#!/usr/bin/env python3
"""Discover source PDFs for additional speleological journals/publications.

This module only builds a source manifest. It does not import article records into
the existing bibliography, so new journals can be inspected before they affect the
public dataset.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = BASE_DIR / "data" / "journal_sources_manifest.json"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SOURCE_DOMAIN_PRIORITY = {
    "sss.sk": 1,
    "www.sss.sk": 1,
    "ssj.sk": 2,
    "www.ssj.sk": 2,
    "smopaj.sk": 3,
    "www.smopaj.sk": 3,
    "archiv.smopaj.sk": 4,
}


@dataclass(frozen=True)
class Link:
    url: str
    text: str = ""


class AnchorLinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[Link] = []
        self._href: str | None = None
        self._title = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_by_name = dict(attrs)
        href = attrs_by_name.get("href")
        if href:
            self._href = urljoin(self.base_url, html.unescape(href))
            self._title = html.unescape(attrs_by_name.get("title") or "")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        text = normalize_spaces("".join(self._text)) or normalize_spaces(self._title)
        self.links.append(Link(url=self._href, text=text))
        self._href = None
        self._title = ""
        self._text = []


class TextContentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = normalize_spaces(data)
        if text:
            self.parts.append(text)


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_ascii(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return normalize_spaces(text)


def slug(value: str) -> str:
    return normalize_ascii(value).replace(" ", "_").strip("_")


def extract_links(html_text: str, base_url: str) -> list[Link]:
    parser = AnchorLinkParser(base_url)
    parser.feed(html_text)
    return parser.links


def extract_text(html_text: str) -> str:
    parser = TextContentParser()
    parser.feed(html_text)
    return normalize_spaces(" ".join(parser.parts))


def is_pdf_url(url: str) -> bool:
    return url_filename(url).lower().endswith(".pdf")


def url_filename(url: str) -> str:
    parsed = urlparse(url)
    query_filename = parse_qs(parsed.query).get("filename", [""])[0]
    if query_filename:
        return Path(query_filename).name
    return unquote(Path(parsed.path).name)


def infer_slovensky_kras_year_from_volume(volume: str) -> int | None:
    volume_number = int(volume)
    if volume_number >= 42:
        return volume_number + 1962
    return None


def normalize_slovensky_kras_issue(value: str | None) -> str:
    issue = normalize_ascii(value or "").replace("_", "-").replace("/", "-").replace(" ", "-")
    if issue in {"supplementum", "suppl"}:
        return "suppl"
    return issue


def source_domain_priority(url: str) -> int:
    host = urlparse(url).netloc.casefold()
    return SOURCE_DOMAIN_PRIORITY.get(host, 50)


def source_priority(source: dict[str, Any], link_url: str) -> int:
    configured = source.get("priority")
    if configured is not None:
        return int(configured)
    return source_domain_priority(link_url)


def compile_patterns(source: dict[str, Any], key: str) -> list[re.Pattern[str]]:
    return [re.compile(pattern, re.I) for pattern in source.get(key, [])]


def source_allows_link(source: dict[str, Any], link: Link) -> bool:
    blob = f"{link.url} {link.text}"
    includes = compile_patterns(source, "include_patterns")
    required = compile_patterns(source, "required_patterns")
    excludes = compile_patterns(source, "exclude_patterns")
    if includes and not any(pattern.search(blob) for pattern in includes):
        return False
    if required and not all(pattern.search(blob) for pattern in required):
        return False
    if any(pattern.search(blob) for pattern in excludes):
        return False
    return True


def parse_slovensky_kras_identity(text: str, url: str, context: str = "") -> dict[str, Any] | None:
    filename = Path(url_filename(url)).stem
    lowered = filename.casefold()
    full_context = normalize_spaces(f"{text} {url} {context}")
    source_blob = normalize_spaces(f"{text} {filename} {url} {context}")
    is_individual_article_pdf = bool(re.match(r"acs_\d+_s\d+", lowered, re.I))

    file_match = re.fullmatch(
        r"(?:slovensky_kras_)?(?P<volume>\d{1,2})_(?P<year1>\d{4})(?:_(?P<year2>\d{4}))?(?:_(?P<issue>[12]|supl_?1))?",
        lowered,
    )
    if file_match:
        volume = file_match.group("volume")
        year1 = file_match.group("year1")
        year2 = file_match.group("year2")
        issue = (file_match.group("issue") or "").replace("_", "-")
        if issue.startswith("supl"):
            issue = "suppl-1"
        year_label = f"{year1}-{year2}" if year2 else year1
        issue_key = f"{volume}_{year_label}"
        if issue:
            issue_key = f"{issue_key}_{issue}"
        return {
            "issue_key": issue_key,
            "volume": volume,
            "year": int(year2 or year1),
            "year_label": year_label,
            "issue": issue,
            "item_type": "issue",
            "pdf_page_offset": 0,
        }

    if not is_individual_article_pdf:
        new_page_patterns = [
            re.compile(
                r"slovensk[ýy]\s+kras\s+"
                r"(?P<volume>\d{1,2})\s*[-_/]\s*"
                r"(?P<issue>1\s*[_/]\s*2|[12])\s*[-_/]\s*"
                r"(?P<year>\d{4})",
                re.I,
            ),
            re.compile(
                r"slovensk[ýy]\s+kras\s+"
                r"(?P<volume>\d{1,2})\s+"
                r"(?P<issue>supplementum|suppl\.?)(?:\s+(?P<year>\d{4}))?",
                re.I,
            ),
            re.compile(
                r"(?:\bsk\b|kras|zborn[ií]k|slovensk[ýy]\s+kras)[^\d]{0,20}"
                r"(?P<volume>\d{2})\s*[-_/ ]\s*"
                r"(?P<issue>1\s*[_/]\s*2|[12])\s*[-_/ ]\s*"
                r"(?P<year>20\d{2}|19\d{2})",
                re.I,
            ),
            re.compile(
                r"(?:\bsk\b|kras|zborn[ií]k|slovensk[ýy]\s+kras)[^\d]{0,20}"
                r"(?P<volume>\d{2})\s*[-_/ ]\s*"
                r"(?P<issue>supplementum|suppl\.?)"
                r"(?:\s*[-_/ ]\s*(?P<year>20\d{2}|19\d{2}))?",
                re.I,
            ),
            re.compile(
                r"(?:\bsk\b|kras|zborn[ií]k|slovensk[ýy]\s+kras)[^\d]{0,20}"
                r"(?P<volume>\d{2})\s*[-_/ ]\s*"
                r"(?P<year>20\d{2}|19\d{2})",
                re.I,
            ),
        ]
        for pattern in new_page_patterns:
            new_page_match = pattern.search(source_blob)
            if not new_page_match:
                continue
            groups = new_page_match.groupdict()
            volume = groups["volume"]
            issue = normalize_slovensky_kras_issue(groups.get("issue"))
            year_value = groups.get("year")
            inferred_year = int(year_value) if year_value else infer_slovensky_kras_year_from_volume(volume)
            if inferred_year:
                issue_key = f"{volume}_{inferred_year}"
                if issue:
                    issue_key = f"{issue_key}_{issue}"
                return {
                    "issue_key": issue_key,
                    "volume": volume,
                    "year": inferred_year,
                    "year_label": str(inferred_year),
                    "issue": issue,
                    "item_type": "issue",
                    "pdf_page_offset": 0,
                }

    context_match = re.search(
        r"slovensk[ýy]\s+kras\s+(?P<volume>\d{1,2})(?:\s+suppl\.?\s*(?P<suppl>\d+))?\s+(?P<year>\d{4})",
        full_context,
        re.I,
    )
    if not context_match:
        return None

    volume = context_match.group("volume")
    year = context_match.group("year")
    issue = f"suppl-{context_match.group('suppl')}" if context_match.group("suppl") else ""
    item_type = "article_pdf" if is_individual_article_pdf else "issue"
    issue_key = f"{volume}_{year}"
    if issue:
        issue_key = f"{issue_key}_{issue}"
    if item_type == "article_pdf":
        issue_key = f"{issue_key}_{slug(filename)}"

    return {
        "issue_key": issue_key,
        "volume": volume,
        "year": int(year),
        "year_label": year,
        "issue": issue,
        "item_type": item_type,
        "pdf_page_offset": 0,
    }


def parse_aragonit_identity(text: str, url: str, context: str = "") -> dict[str, Any] | None:
    filename = Path(url_filename(url)).stem
    blob = normalize_spaces(f"{filename} {text} {context}")
    match = re.search(r"aragon(?:it)?[_\s-]*(?P<volume>\d{1,2})(?:[_\s/-]+(?P<issue>\d(?:-\d)?))?", blob, re.I)
    if not match:
        match = re.search(r"č\.\s*(?P<volume>\d{1,2})(?:/(?P<issue>\d(?:-\d)?))?", blob, re.I)
    if not match:
        return None
    volume = match.group("volume")
    issue = match.group("issue") or ""
    year_match = re.search(
        rf"(?:ročník|rocnik|Aragonit\s+č\.)\s*{re.escape(volume)}(?:\s*[/_-]\s*{re.escape(issue)})?[^\d]{{0,40}}(?P<year>19\d{{2}}|20\d{{2}})",
        context,
        re.I,
    )
    if not year_match:
        year_match = re.search(rf"\bAragonit\s+{re.escape(volume)}\s*[/_-]\s*{re.escape(issue)}\s+(?P<year>19\d{{2}}|20\d{{2}})\b", context, re.I)
    year = int(year_match.group("year")) if year_match else int(volume) + 1995
    return {
        "issue_key": f"{volume}_{issue}" if issue else volume,
        "volume": volume,
        "year": year,
        "year_label": str(year) if year else "",
        "issue": issue,
        "item_type": "issue",
        "pdf_page_offset": 2,
    }


def parse_other_publication_identity(text: str, url: str, context: str = "") -> dict[str, Any]:
    filename = Path(url_filename(url)).stem
    label = normalize_spaces(text) or normalize_spaces(context) or filename
    key = slug(label) or slug(filename)
    return {
        "issue_key": key,
        "volume": "",
        "year": None,
        "year_label": "",
        "issue": "",
        "item_type": "publication",
        "pdf_page_offset": 0,
    }


def parse_identity(journal_id: str, text: str, url: str, context: str = "") -> dict[str, Any] | None:
    if journal_id == "slovensky_kras":
        return parse_slovensky_kras_identity(text, url, context)
    if journal_id == "aragonit":
        return parse_aragonit_identity(text, url, context)
    if journal_id == "ine_publikacie":
        return parse_other_publication_identity(text, url, context)
    return None


def build_manifest_item(
    journal_id: str,
    journal_title: str,
    journal_short_title: str,
    source: dict[str, Any],
    link: Link,
    context: str = "",
    detail_url: str = "",
) -> dict[str, Any] | None:
    identity = parse_identity(journal_id, link.text, link.url, context)
    if not identity:
        return None
    priority = source_priority(source, link.url)
    return {
        "journal_id": journal_id,
        "journal_title": journal_title,
        "journal_short_title": journal_short_title,
        "issue_key": identity["issue_key"],
        "volume": identity.get("volume") or "",
        "year": identity.get("year"),
        "year_label": identity.get("year_label") or "",
        "issue": identity.get("issue") or "",
        "item_type": identity.get("item_type") or "issue",
        "pdf_url": link.url,
        "label": normalize_spaces(link.text),
        "source_id": source["source_id"],
        "source_url": source["url"],
        "source_priority": priority,
        "source_domain_priority": source_domain_priority(link.url),
        "detail_url": detail_url,
        "pdf_page_offset": int(identity.get("pdf_page_offset") or 0),
    }


def candidate_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("journal_id") or ""),
        str(item.get("item_type") or ""),
        str(item.get("issue_key") or ""),
    )


def choose_best_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate_key(candidate), []).append(candidate)

    selected: list[dict[str, Any]] = []
    for items in grouped.values():
        ordered = sorted(
            items,
            key=lambda item: (
                int(item.get("source_priority") or 50),
                int(item.get("source_domain_priority") or 50),
                str(item.get("pdf_url") or ""),
            ),
        )
        winner = dict(ordered[0])
        alternatives = [
            {
                "pdf_url": item["pdf_url"],
                "source_id": item["source_id"],
                "source_priority": item["source_priority"],
                "detail_url": item.get("detail_url") or "",
            }
            for item in ordered[1:]
        ]
        if alternatives:
            winner["alternatives"] = alternatives
        selected.append(winner)

    return sorted(
        selected,
        key=lambda item: (
            str(item.get("journal_id") or ""),
            int(item["year"]) if item.get("year") is not None else 9999,
            str(item.get("volume") or ""),
            str(item.get("issue") or ""),
            str(item.get("issue_key") or ""),
        ),
    )


def default_journals() -> list[dict[str, Any]]:
    return [
        {
            "journal_id": "slovensky_kras",
            "title": "Slovenský kras",
            "short_title": "Slovenský kras",
            "pdf_page_offset": 0,
            "sources": [
                {
                    "source_id": "ssj_slovensky_kras",
                    "url": "https://www.ssj.sk/sk/slovensky-kras",
                    "priority": 2,
                    "mode": "detail_pages",
                    "detail_include_patterns": [r"/sk/clanok/\d+-slovensky-kras"],
                    "include_patterns": [r"\.pdf"],
                    "exclude_patterns": [r"ACS_\d+_S\d+"],
                },
                {
                    "source_id": "smopaj_slovensky_kras_new",
                    "url": "https://www.smopaj.sk/sk/slovensky-kras",
                    "priority": 3,
                    "mode": "direct",
                    "include_patterns": [r"documentloader\.php.*filename=.*\.pdf"],
                },
                {
                    "source_id": "smopaj_slovensky_kras",
                    "url": "http://archiv.smopaj.sk/index.php/Online_publik%C3%A1cie",
                    "priority": 4,
                    "mode": "direct",
                    "include_patterns": [r"Slovensky_kras/.*\.pdf"],
                },
            ],
        },
        {
            "journal_id": "aragonit",
            "title": "Aragonit",
            "short_title": "Aragonit",
            "pdf_page_offset": 2,
            "sources": [
                {
                    "source_id": "ssj_aragonit",
                    "url": "https://www.ssj.sk/sk/casopis-aragonit",
                    "priority": 2,
                    "mode": "detail_pages",
                    "detail_include_patterns": [r"/sk/clanok/\d+-casopis-aragonit"],
                    "include_patterns": [r"\.pdf"],
                    "required_patterns": [r"Cel[eé]\s+č[ií]slo|komplet|cely|cel[yý]|_web"],
                    "exclude_patterns": [r"obal", r"obalka", r"uvod_str"],
                },
            ],
        },
        {
            "journal_id": "ine_publikacie",
            "title": "Iné publikácie",
            "short_title": "Iné publikácie",
            "pdf_page_offset": 0,
            "sources": [
                {
                    "source_id": "ssj_ine_publikacie",
                    "url": "https://www.ssj.sk/sk/ine-publikacie",
                    "priority": 2,
                    "mode": "detail_pages",
                    "detail_include_patterns": [r"/sk/clanok/\d+"],
                    "include_patterns": [r"\.pdf"],
                    "exclude_patterns": [r"spravodaj", r"slovensky[_\s-]*kras", r"aragonit"],
                },
                {
                    "source_id": "smopaj_other_publications",
                    "url": "http://archiv.smopaj.sk/index.php/Online_publik%C3%A1cie",
                    "priority": 3,
                    "mode": "direct",
                    "include_patterns": [r"\.pdf"],
                    "exclude_patterns": [r"Spravodaj_SSS/", r"spravodaj", r"Slovensky_kras/", r"slovensk[ýy]\s+kras"],
                },
            ],
        },
    ]


def journal_by_id(journal_id: str) -> dict[str, Any]:
    for journal in default_journals():
        if journal["journal_id"] == journal_id:
            return journal
    raise KeyError(f"Unknown journal id: {journal_id}")


def source_by_id(source_id: str) -> dict[str, Any]:
    for journal in default_journals():
        for source in journal["sources"]:
            if source["source_id"] == source_id:
                return source
    raise KeyError(f"Unknown source id: {source_id}")


def requests_fetch_text(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text


def unique_links(links: list[Link]) -> list[Link]:
    seen: set[str] = set()
    result: list[Link] = []
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        result.append(link)
    return result


def discover_source_candidates(
    journal: dict[str, Any],
    source: dict[str, Any],
    fetch_text: Callable[[str], str],
    detail_limit: int | None = None,
) -> list[dict[str, Any]]:
    source_html = fetch_text(source["url"])
    links = extract_links(source_html, source["url"])
    mode = source.get("mode", "direct")
    candidates: list[dict[str, Any]] = []

    if mode == "direct":
        for link in unique_links(links):
            if is_pdf_url(link.url) and source_allows_link(source, link):
                item = build_manifest_item(
                    journal["journal_id"],
                    journal["title"],
                    journal["short_title"],
                    source,
                    link,
                )
                if item:
                    candidates.append(item)
        return candidates

    detail_patterns = compile_patterns(source, "detail_include_patterns")
    detail_links = [
        link
        for link in links
        if detail_patterns and any(pattern.search(link.url) for pattern in detail_patterns)
    ]
    for detail_link in unique_links(detail_links)[:detail_limit]:
        detail_html = fetch_text(detail_link.url)
        pdf_links = extract_links(detail_html, detail_link.url)
        detail_text = extract_text(detail_html)
        context = normalize_spaces(f"{detail_link.text} {detail_link.url} {detail_text[:8000]}")
        for pdf_link in pdf_links:
            if is_pdf_url(pdf_link.url) and source_allows_link(source, pdf_link):
                item = build_manifest_item(
                    journal["journal_id"],
                    journal["title"],
                    journal["short_title"],
                    source,
                    pdf_link,
                    context=context,
                    detail_url=detail_link.url,
                )
                if item:
                    candidates.append(item)
    return candidates


def discover_journal_sources(
    journals: list[dict[str, Any]] | None = None,
    fetch_text: Callable[[str], str] = requests_fetch_text,
    detail_limit: int | None = None,
) -> dict[str, Any]:
    selected_journals = journals or default_journals()
    candidates: list[dict[str, Any]] = []
    source_errors: list[dict[str, str]] = []

    for journal in selected_journals:
        for source in journal["sources"]:
            try:
                candidates.extend(discover_source_candidates(journal, source, fetch_text, detail_limit))
            except Exception as exc:  # pragma: no cover - exercised by live CLI, unit tests use deterministic fetchers.
                source_errors.append(
                    {
                        "journal_id": journal["journal_id"],
                        "source_id": source["source_id"],
                        "url": source["url"],
                        "error": str(exc),
                    }
                )

    items = choose_best_candidates(candidates)
    journal_counts = {}
    for item in items:
        journal_counts[item["journal_id"]] = journal_counts.get(item["journal_id"], 0) + 1

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_priority": ["sss.sk", "ssj.sk", "smopaj.sk", "archiv.smopaj.sk"],
        "summary": {
            "items": len(items),
            "raw_candidates": len(candidates),
            "journals": journal_counts,
            "source_errors": len(source_errors),
        },
        "journals": [
            {
                "journal_id": journal["journal_id"],
                "title": journal["title"],
                "short_title": journal["short_title"],
                "pdf_page_offset": journal.get("pdf_page_offset", 0),
            }
            for journal in selected_journals
        ],
        "items": items,
        "source_errors": source_errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--journal",
        action="append",
        choices=[journal["journal_id"] for journal in default_journals()],
        help="Discover only this journal/publication group. Can be repeated.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=None,
        help="Limit crawled detail pages per source; useful for quick smoke checks.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print manifest JSON to stdout instead of writing the output file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    journals = [journal_by_id(journal_id) for journal_id in args.journal] if args.journal else default_journals()
    manifest = discover_journal_sources(journals=journals, detail_limit=args.detail_limit)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.print:
        print(payload)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), **manifest["summary"]}, ensure_ascii=False, indent=2))

    if manifest["source_errors"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
