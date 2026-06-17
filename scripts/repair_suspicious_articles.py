#!/usr/bin/env python3
"""Audit and repair suspicious bibliography records.

The deterministic repair handles common parser spillovers such as:

Title, 2 obr., lit., s. 45 – 51 Abstract text...

Unresolved records are exported as AI candidates so Codex can inspect the PDF
issue text in a separate, explicit pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FRONTEND_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
AI_CANDIDATES_PATH = BASE_DIR / "data" / "exports" / "suspicious_articles_for_ai.jsonl"
AI_RESULTS_PATH = BASE_DIR / "data" / "exports" / "suspicious_articles_ai_results.jsonl"
RAW_BIBLIOGRAPHY_PATH = BASE_DIR / "data" / "raw_text.txt"
URL_MAP_PATH = BASE_DIR / "data" / "urls_map.json"
HISTORIC_LAST_ARTICLE_ID = 2535
AI_APPLY_KEYS = ("title", "authors", "pages", "extras", "abstract")
PAGE_VALUE_PATTERN = r"\d+\s*(?:(?:[–-]|\ba\b)\s*\d+\s*)*"
PAGE_SPILLOVER_RE = re.compile(
    r"^(?P<title>.+?),\s*(?P<meta>(?:(?:\d+\s*(?:obr\.|tab\.|pl\.\s*j\.|pl\.)|lit\.|tab\.|mapa|mapy|pl\. j\.)\s*,?\s*)*)"
    rf"s\.?\s*(?P<pages>{PAGE_VALUE_PATTERN})\s+(?P<tail>.+)$",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"^\s*Ročník\s+(\d{4})(?:\s*\(([^)]+)\))?\s*$", re.IGNORECASE)
ISSUE_RE = re.compile(r"^\s*Číslo\s+(.+?)\s*$", re.IGNORECASE)
SPECIAL_ISSUE_RE = re.compile(r"^\s*Zvláštne vydanie(?:\s*\((.+)\))?\s*$", re.IGNORECASE)
ARTICLE_START_RE = re.compile(r"^(\d+)\.\s+(.+)$")
PAGE_SUFFIX_RE = re.compile(
    rf"^(?P<head>.+?)(?:,\s*|\s+)s\.?\s*(?P<pages>{PAGE_VALUE_PATTERN})(?:\s*(?P<postscript>\([^)]+\)))?\s*$",
    re.IGNORECASE,
)
BARE_PAGE_SUFFIX_RE = re.compile(
    r"^(?P<head>.+?),\s*(?P<pages>\d+\s*(?:(?:[–-]|\ba\b)\s*\d+\s*)+)\s*$",
    re.IGNORECASE,
)
NO_COLON_AUTHOR_RE = re.compile(
    r"^(?P<author>[^,]+,\s*[A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž]\.)\s+(?P<title>.+)$"
)
EXTRA_SUFFIX_RE = re.compile(
    r",\s*(?P<extra>"
    r"\d+\s*pl\.\s*j\.\s*\+\s*samostatná príloha[^,]+|"
    r"lit\.\s*\+\s*samostatná príloha[^,]+|"
    r"\d+\s*(?:obr\.|tab\.|fot\.|pl\.\s*j\.|pl\.)|"
    r"res\.|lit\.|tab\.|map\."
    r")\s*$",
    re.IGNORECASE,
)
AUTHOR_SPLIT_RE = re.compile(
    r",\s*(?=[A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ][^,.]{2,},\s*[A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ])"
)
SECTION_HEADINGS = {
    "Aktuality",
    "Archeológia",
    "Biospeleológia",
    "Činnosť oblastných skupín",
    "Činnosť odborných komisií",
    "Dokumentácia",
    "História",
    "Jaskyniarska záchranná služba",
    "Jubilanti",
    "Krátke správy po uzávierke",
    "Literatúra",
    "Organizačné správy",
    "Ochrana jaskýň",
    "Recenzie",
    "Rôzne",
    "Správy",
    "Spoločenské správy",
    "Technika",
    "Technika a výstroj",
    "Výskum",
    "Výskum a prieskum",
    "Z literatúry",
    "Z tvorby našich autorov",
    "Zahraničie",
    "Zahraničné cesty",
    "Zaujímavosti",
    "Zaujímavosti zo speleológie",
}


def read_articles(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected a list in {path}")
    return data


def write_articles(path: Path, articles: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(articles, handle, ensure_ascii=False, indent=2)


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected an object in {path}")
    return data


def clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace("\x0c", "").strip())


def normalize_issue(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().replace(" – ", "-")).replace("–", "-")


def url_map_issue_token(issue: str) -> str | None:
    text = normalize_issue(str(issue or "")).casefold()
    if not text:
        return None
    if "kongres" in text:
        return "kongres"
    if "mimoriadne" in text and not re.search(r"\d", text):
        return "mimoriadne"
    numbers = re.findall(r"\d+", text)
    if not numbers:
        return None
    if len(numbers) >= 2 and re.match(r"^\s*\d+\s*-\s*\d+", text):
        return f"{numbers[0]}-{numbers[1]}"
    return numbers[0]


def normalize_pages(value: str) -> str:
    text = re.sub(r"\s*[–-]\s*", "-", value.strip())
    text = re.sub(r"\s+\ba\b\s+", " a ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def page_bounds(pages: str) -> tuple[int | None, int | None]:
    numbers = [int(value) for value in re.findall(r"\d+", normalize_pages(pages or ""))]
    if not numbers:
        return None, None
    return numbers[0], numbers[-1]


def clean_meta_items(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def is_junk_bibliography_line(line: str) -> bool:
    text = clean_line(line)
    if not text:
        return True
    if text == "Bibliografia Spravodaja SSS":
        return True
    if text.isdigit():
        return True
    if text.casefold() in {"zoznam článkov", "zoznam článkov", "predslov", "anotácia"}:
        return True
    if re.match(r"^Ročník\s+\d+$", text, re.IGNORECASE):
        return True
    if re.match(r"^Summary\b", text):
        return True
    return False


def is_section_heading(line: str) -> bool:
    return clean_line(line) in SECTION_HEADINGS


def starts_as_header_continuation(line: str) -> bool:
    text = clean_line(line)
    if not text:
        return False
    if text.lower().startswith(("isbn", "issn")):
        return True
    return text[0].islower() or text[0] in "-–+"


def page_suffix_match(header: str) -> re.Match[str] | None:
    match = PAGE_SUFFIX_RE.match(header)
    if match:
        return match
    match = BARE_PAGE_SUFFIX_RE.match(header)
    if match and not match.group("head").strip().casefold().endswith(("isbn", "issn")):
        return match
    return None


def split_authors(authors_text: str) -> list[str]:
    authors_text = clean_line(authors_text)
    if not authors_text:
        return ["Anonymus"]
    parts = [part.strip() for part in AUTHOR_SPLIT_RE.split(authors_text) if part.strip()]
    return parts or [authors_text]


def split_title_extras(value: str) -> tuple[str, list[str]]:
    title = clean_line(value)
    extras: list[str] = []
    while True:
        match = EXTRA_SUFFIX_RE.search(title)
        if not match:
            break
        extras.append(clean_line(match.group("extra")))
        title = title[: match.start()].strip()
    extras.reverse()
    return title, extras


def strip_trailing_section_headings(lines: list[str]) -> list[str]:
    cleaned = [clean_line(line) for line in lines if clean_line(line)]
    while cleaned and is_section_heading(cleaned[-1]):
        cleaned.pop()
    return cleaned


def no_page_header_line_count(lines: list[str]) -> int:
    count = 1
    while count < len(lines):
        previous = clean_line(lines[count - 1])
        current = clean_line(lines[count])
        if is_section_heading(current):
            break
        if previous.endswith((",", "-", "–", "+", "(")) or starts_as_header_continuation(current):
            count += 1
            continue
        break
    return count


def parse_authoritative_segment(
    article_id: int,
    lines: list[str],
    year: int,
    volume: str,
    issue: str,
) -> dict[str, Any] | None:
    if not lines:
        return None

    header_line_count = 0
    page_match: re.Match[str] | None = None
    for index in range(1, len(lines) + 1):
        header = clean_line(" ".join(lines[:index]))
        page_match = page_suffix_match(header)
        if page_match:
            header_line_count = index
            break

    if not page_match:
        header_line_count = no_page_header_line_count(lines)
        header = clean_line(" ".join(lines[:header_line_count]))
        pages = ""
        header_no_pages = header
    else:
        header = clean_line(" ".join(lines[:header_line_count]))
        pages = normalize_pages(page_match.group("pages"))
        header_no_pages = clean_line(page_match.group("head")).rstrip(",")
    postscript = clean_line(page_match.group("postscript")) if page_match and "postscript" in page_match.groupdict() and page_match.group("postscript") else ""

    number_match = ARTICLE_START_RE.match(header_no_pages)
    if not number_match:
        return None
    content = number_match.group(2).strip()

    colon_index = content.find(":")
    if colon_index >= 0:
        authors = split_authors(content[:colon_index])
        title_and_extras = content[colon_index + 1 :].strip()
    else:
        author_match = NO_COLON_AUTHOR_RE.match(content)
        if author_match:
            authors = split_authors(author_match.group("author"))
            title_and_extras = author_match.group("title").strip()
        else:
            authors = ["Anonymus"]
            title_and_extras = content

    title, extras = split_title_extras(title_and_extras)
    abstract_lines = strip_trailing_section_headings(lines[header_line_count:])
    if postscript:
        abstract_lines.insert(0, postscript)
    return {
        "id": article_id,
        "authors": authors,
        "title": title,
        "pages": pages,
        "extras": extras,
        "year": year,
        "volume": volume,
        "issue": issue,
        "abstract": clean_line(" ".join(abstract_lines)),
    }


def parse_authoritative_bibliography_text(text: str) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    current_year = 1970
    current_volume = "I."
    current_issue = "1"
    current_id: int | None = None
    current_lines: list[str] = []
    last_saved_id = 0

    def save_current() -> None:
        nonlocal current_id, current_lines, last_saved_id
        if current_id is None:
            return
        record = parse_authoritative_segment(
            current_id,
            current_lines,
            current_year,
            current_volume,
            current_issue,
        )
        if record:
            records[current_id] = record
            last_saved_id = current_id
        current_id = None
        current_lines = []

    for raw_line in text.splitlines():
        line = clean_line(raw_line)
        if is_junk_bibliography_line(line):
            continue

        year_match = YEAR_RE.match(line)
        if year_match:
            save_current()
            current_year = int(year_match.group(1))
            current_volume = year_match.group(2) or ""
            continue

        issue_match = ISSUE_RE.match(line)
        if issue_match:
            save_current()
            current_issue = normalize_issue(issue_match.group(1))
            continue

        special_issue_match = SPECIAL_ISSUE_RE.match(line)
        if special_issue_match:
            save_current()
            detail = special_issue_match.group(1)
            current_issue = "zvláštne vydanie" + (f" ({detail})" if detail else "")
            continue

        start_match = ARTICLE_START_RE.match(line)
        if start_match:
            article_id = int(start_match.group(1))
            expected = (current_id + 1) if current_id is not None else (last_saved_id + 1)
            if last_saved_id == 0 and current_id is None:
                expected = article_id
            if article_id == expected:
                save_current()
                current_id = article_id
                current_lines = [line]
                continue

        if current_id is not None:
            current_lines.append(line)

    save_current()
    return records


def load_authoritative_records(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    records = parse_authoritative_bibliography_text(path.read_text(encoding="utf-8", errors="replace"))
    if len(records) < 2500:
        raise RuntimeError(f"Parsed only {len(records)} historic records from {path}")
    return records


def infer_pdf_offset(article: dict[str, Any], articles_by_pdf: dict[str, list[dict[str, Any]]]) -> int | None:
    pdf_url = str(article.get("pdf_url") or "")
    offsets: list[int] = []
    for sibling in articles_by_pdf.get(pdf_url, []):
        page_start, _ = page_bounds(str(sibling.get("pages") or ""))
        pdf_page_start = sibling.get("pdf_page_start")
        if page_start is None or not isinstance(pdf_page_start, int):
            continue
        offsets.append(pdf_page_start - page_start)
    if not offsets:
        return None
    return Counter(offsets).most_common(1)[0][0]


def apply_pdf_page_bounds(article: dict[str, Any], articles_by_pdf: dict[str, list[dict[str, Any]]]) -> None:
    page_start, page_end = page_bounds(str(article.get("pages") or ""))
    offset = infer_pdf_offset(article, articles_by_pdf)
    if page_start is None:
        article["pdf_page_start"] = None
        article["pdf_page_end"] = None
    elif offset is not None:
        article["pdf_page_start"] = page_start + offset
        article["pdf_page_end"] = (page_end or page_start) + offset


def apply_authoritative_records(
    articles: list[dict[str, Any]],
    authoritative_records: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not authoritative_records:
        return []

    changes: list[dict[str, Any]] = []
    authoritative_keys = ("authors", "title", "pages", "extras", "year", "volume", "issue", "abstract")
    for article in articles:
        article_id = article.get("id")
        if not isinstance(article_id, int) or article_id > HISTORIC_LAST_ARTICLE_ID:
            continue
        authoritative = authoritative_records.get(article_id)
        if not authoritative:
            continue
        old = {key: article.get(key) for key in authoritative_keys}
        for key in authoritative_keys:
            if (
                key == "pages"
                and not authoritative.get(key)
                and article.get("page_source") == "codex_ai_fallback_pages_only"
            ):
                continue
            article[key] = authoritative.get(key)
        new = {key: article.get(key) for key in authoritative_keys}
        if old != new:
            changes.append({"id": article_id, "source": "original_bibliography", "old": old, "new": new})

    articles_by_pdf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        articles_by_pdf[str(article.get("pdf_url") or "")].append(article)
    for change in changes:
        article = next(item for item in articles if item.get("id") == change["id"])
        old_pages = {
            "pdf_page_start": article.get("pdf_page_start"),
            "pdf_page_end": article.get("pdf_page_end"),
        }
        apply_pdf_page_bounds(article, articles_by_pdf)
        new_pages = {
            "pdf_page_start": article.get("pdf_page_start"),
            "pdf_page_end": article.get("pdf_page_end"),
        }
        if old_pages != new_pages:
            change["old"].update(old_pages)
            change["new"].update(new_pages)

    return changes


def sync_pdf_urls_from_map(articles: list[dict[str, Any]], url_map: dict[str, Any]) -> list[dict[str, Any]]:
    if not url_map:
        return []

    changes: list[dict[str, Any]] = []
    for article in articles:
        year = article.get("year")
        token = url_map_issue_token(str(article.get("issue") or ""))
        if not isinstance(year, int) or not token:
            continue
        key = f"{year}_{token}"
        mapped_url = str(url_map.get(key) or "")
        if not mapped_url or mapped_url == str(article.get("pdf_url") or ""):
            continue
        old = {
            "pdf_url": article.get("pdf_url"),
            "pdf_page_start": article.get("pdf_page_start"),
            "pdf_page_end": article.get("pdf_page_end"),
        }
        article["pdf_url"] = mapped_url
        article["pdf_page_start"] = None
        article["pdf_page_end"] = None
        changes.append({"id": article.get("id"), "source": "urls_map", "old": old, "new": {"pdf_url": mapped_url}})

    if changes:
        articles_by_pdf: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for article in articles:
            articles_by_pdf[str(article.get("pdf_url") or "")].append(article)
        changed_ids = {change["id"] for change in changes}
        for article in articles:
            if article.get("id") not in changed_ids:
                continue
            apply_pdf_page_bounds(article, articles_by_pdf)
            for change in changes:
                if change["id"] == article.get("id"):
                    change["new"].update({
                        "pdf_page_start": article.get("pdf_page_start"),
                        "pdf_page_end": article.get("pdf_page_end"),
                    })
                    break
    return changes


def suspicion_reasons(article: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    title = str(article.get("title") or "")
    pages = str(article.get("pages") or "").strip()
    if not pages:
        reasons.append("missing_pages")
    if len(title) > 220 and (not pages or re.search(r",\s*s\.\s*\d+", title)):
        reasons.append("long_title")
    if re.search(r",\s*s\.\s*\d+", title):
        reasons.append("embedded_pages_in_title")
    if "\n" in title:
        reasons.append("multiline_title")
    return reasons


def repair_article(
    article: dict[str, Any],
    articles_by_pdf: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    title = str(article.get("title") or "")
    match = PAGE_SPILLOVER_RE.match(title)
    if not match:
        return None

    old = {
        "title": article.get("title"),
        "extras": list(article.get("extras") or []),
        "pages": article.get("pages"),
        "abstract": article.get("abstract"),
        "pdf_page_start": article.get("pdf_page_start"),
        "pdf_page_end": article.get("pdf_page_end"),
    }

    article["title"] = match.group("title").strip()
    article["pages"] = normalize_pages(match.group("pages"))
    meta_items = clean_meta_items(match.group("meta"))
    if meta_items:
        existing = [item for item in article.get("extras") or [] if item not in meta_items]
        article["extras"] = existing + meta_items
    tail = match.group("tail").strip()
    if tail and not str(article.get("abstract") or "").strip():
        article["abstract"] = tail

    page_start, page_end = page_bounds(article["pages"])
    apply_pdf_page_bounds(article, articles_by_pdf)

    return {"id": article.get("id"), "old": old, "new": {key: article.get(key) for key in old}}


def repair_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    articles_by_pdf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        articles_by_pdf[str(article.get("pdf_url") or "")].append(article)

    changes: list[dict[str, Any]] = []
    for article in articles:
        if not suspicion_reasons(article):
            continue
        change = repair_article(article, articles_by_pdf)
        if change:
            changes.append(change)
    return changes


def load_pdf_issue_text(article: dict[str, Any], max_chars: int = 12000) -> str:
    pdf_url = str(article.get("pdf_url") or "")
    if not pdf_url:
        return ""
    filename = pdf_url.rsplit("/", 1)[-1]
    matches = sorted((BASE_DIR / "data" / "pdf_text").glob(f"*_{filename}.txt"))
    if not matches:
        return ""
    return matches[0].read_text(encoding="utf-8", errors="replace")[:max_chars]


def build_ai_candidate(article: dict[str, Any], reasons: list[str], issue_text: str) -> dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "authors": {"type": "array", "items": {"type": "string"}},
            "pages": {"type": "string"},
            "extras": {"type": "array", "items": {"type": "string"}},
            "abstract": {"type": "string"},
            "confidence": {"type": "number"},
            "needs_human_review": {"type": "boolean"},
        },
        "required": ["title", "authors", "pages", "extras", "abstract", "confidence", "needs_human_review"],
    }
    prompt = (
        "Skontroluj bibliografický záznam článku Spravodaja SSS podľa textu PDF čísla. "
        "Nevymýšľaj údaje. Ak nevieš overiť strany alebo názov, označ needs_human_review=true.\n\n"
        f"Podozrivé dôvody: {', '.join(reasons)}\n"
        f"Záznam JSON:\n{json.dumps(article, ensure_ascii=False, indent=2)}\n\n"
        f"Text PDF čísla:\n{issue_text}"
    )
    return {
        "id": article.get("id"),
        "reasons": reasons,
        "pdf_url": article.get("pdf_url"),
        "prompt": prompt,
        "schema": schema,
    }


def write_ai_candidates(articles: list[dict[str, Any]], path: Path) -> list[dict[str, Any]]:
    candidates = []
    for article in articles:
        reasons = suspicion_reasons(article)
        if not reasons:
            continue
        candidates.append(build_ai_candidate(article, reasons, load_pdf_issue_text(article)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    return candidates


def clean_ai_string(value: Any) -> str:
    return clean_line(str(value or ""))


def clean_ai_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_ai_string(item) for item in value if clean_ai_string(item)]
    text = clean_ai_string(value)
    return [text] if text else []


def normalized_title_tokens(value: str) -> set[str]:
    text = unicodedata_normalize(value)
    return {token for token in re.findall(r"[a-z0-9]{2,}", text) if token not in {"ako", "the", "and"}}


def unicodedata_normalize(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def title_similarity(left: str, right: str) -> float:
    left_norm = unicodedata_normalize(left)
    right_norm = unicodedata_normalize(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 1.0
    left_tokens = normalized_title_tokens(left)
    right_tokens = normalized_title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return (2 * len(left_tokens & right_tokens)) / (len(left_tokens) + len(right_tokens))


def ai_confidence(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def apply_ai_result(
    article: dict[str, Any],
    result: dict[str, Any],
    articles_by_pdf: dict[str, list[dict[str, Any]]],
    min_confidence: float,
) -> tuple[dict[str, Any] | None, str]:
    confidence = ai_confidence(result.get("confidence"))
    if result.get("needs_human_review"):
        return None, "needs_human_review"
    if confidence < min_confidence:
        return None, "low_confidence"

    ai_title = clean_ai_string(result.get("title"))
    is_historic = isinstance(article.get("id"), int) and article["id"] <= HISTORIC_LAST_ARTICLE_ID
    if is_historic:
        if ai_title and title_similarity(str(article.get("title") or ""), ai_title) < 0.45:
            return None, "historic_title_mismatch"
        pages = clean_ai_string(result.get("pages"))
        if not pages:
            return None, "missing_ai_pages"
        old = {
            "pages": article.get("pages"),
            "pdf_page_start": article.get("pdf_page_start"),
            "pdf_page_end": article.get("pdf_page_end"),
        }
        article["pages"] = normalize_pages(pages)
        article["page_source"] = "codex_ai_fallback_pages_only"
        article["page_confidence"] = confidence
        apply_pdf_page_bounds(article, articles_by_pdf)
        new = {
            "pages": article.get("pages"),
            "pdf_page_start": article.get("pdf_page_start"),
            "pdf_page_end": article.get("pdf_page_end"),
        }
        if old == new:
            return None, "no_change"
        return {
            "id": article.get("id"),
            "source": "codex_ai_fallback_pages_only",
            "confidence": confidence,
            "old": old,
            "new": new,
        }, "applied"

    old = {key: article.get(key) for key in AI_APPLY_KEYS}
    old["pdf_page_start"] = article.get("pdf_page_start")
    old["pdf_page_end"] = article.get("pdf_page_end")

    if ai_title:
        article["title"] = ai_title

    authors = clean_ai_string_list(result.get("authors"))
    if authors:
        article["authors"] = authors

    pages = clean_ai_string(result.get("pages"))
    if pages:
        article["pages"] = normalize_pages(pages)

    extras = clean_ai_string_list(result.get("extras"))
    article["extras"] = extras

    abstract = clean_ai_string(result.get("abstract"))
    article["abstract"] = abstract

    apply_pdf_page_bounds(article, articles_by_pdf)

    new = {key: article.get(key) for key in AI_APPLY_KEYS}
    new["pdf_page_start"] = article.get("pdf_page_start")
    new["pdf_page_end"] = article.get("pdf_page_end")
    if old == new:
        return None, "no_change"
    return {
        "id": article.get("id"),
        "source": "codex_ai_fallback",
        "confidence": confidence,
        "old": old,
        "new": new,
    }, "applied"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def apply_ai_results_file(
    articles: list[dict[str, Any]],
    results_path: Path,
    min_confidence: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    articles_by_id = {article.get("id"): article for article in articles}
    articles_by_pdf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        articles_by_pdf[str(article.get("pdf_url") or "")].append(article)

    changes: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    for row in read_jsonl(results_path):
        article_id = row.get("id")
        result = row.get("result")
        article = articles_by_id.get(article_id)
        if article is None or not isinstance(result, dict):
            continue
        change, status = apply_ai_result(article, result, articles_by_pdf, min_confidence)
        replay_row = {"id": article_id, "status": status, "source_status": row.get("status")}
        if change:
            changes.append(change)
            replay_row["change"] = change
        result_rows.append(replay_row)
    return changes, result_rows


def run_ai_fallback(
    articles: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    results_path: Path,
    model: str,
    timeout: int,
    min_confidence: float,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from codex_ai_backend import CodexAuthError, run_codex_json

    articles_by_id = {article.get("id"): article for article in articles}
    articles_by_pdf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        articles_by_pdf[str(article.get("pdf_url") or "")].append(article)

    selected = candidates[:limit] if limit is not None else candidates
    changes: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(selected, start=1):
        article_id = candidate.get("id")
        article = articles_by_id.get(article_id)
        if article is None:
            result_rows.append({"id": article_id, "status": "missing_article"})
            continue
        print(f"AI fallback {index}/{len(selected)}: article {article_id}", file=sys.stderr)
        try:
            result = run_codex_json(candidate["prompt"], candidate["schema"], model, timeout)
        except CodexAuthError:
            raise
        except Exception as exc:
            result_rows.append({"id": article_id, "status": "error", "error": str(exc)})
            continue

        change, status = apply_ai_result(article, result, articles_by_pdf, min_confidence)
        result_row = {
            "id": article_id,
            "status": status,
            "reasons": candidate.get("reasons", []),
            "model": model,
            "result": result,
        }
        if change:
            changes.append(change)
            result_row["change"] = change
        result_rows.append(result_row)

    write_jsonl(results_path, result_rows)
    return changes, result_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair suspicious Spravodaj bibliography records.")
    parser.add_argument("--articles", default=str(ARTICLES_PATH), help="Canonical articles JSON.")
    parser.add_argument("--frontend", default=str(FRONTEND_ARTICLES_PATH), help="Frontend articles JSON to sync.")
    parser.add_argument("--ai-candidates", default=str(AI_CANDIDATES_PATH), help="JSONL path for unresolved AI candidates.")
    parser.add_argument("--ai-results", default=str(AI_RESULTS_PATH), help="JSONL path for Codex fallback results.")
    parser.add_argument("--raw-bibliography", default=str(RAW_BIBLIOGRAPHY_PATH), help="Historic Lalkovič bibliography text for authoritative repairs.")
    parser.add_argument("--url-map", default=str(URL_MAP_PATH), help="Issue PDF URL map to resync after issue repairs.")
    parser.add_argument("--no-authoritative", action="store_true", help="Skip repairs from the original historic bibliography.")
    parser.add_argument("--run-ai-fallback", action="store_true", help="Use Codex auth to resolve remaining suspicious records.")
    parser.add_argument("--apply-ai-results", action="store_true", help="Apply existing Codex fallback result JSONL without new AI calls.")
    parser.add_argument("--ai-limit", type=int, default=None, help="Limit Codex fallback records.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.5"), help="Codex fallback model.")
    parser.add_argument("--timeout", type=int, default=300, help="Codex fallback timeout seconds.")
    parser.add_argument("--ai-min-confidence", type=float, default=0.75, help="Minimum confidence for applying AI fallback.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files.")
    args = parser.parse_args()

    articles_path = Path(args.articles)
    frontend_path = Path(args.frontend)
    ai_candidates_path = Path(args.ai_candidates)
    ai_results_path = Path(args.ai_results)
    articles = read_articles(articles_path)
    authoritative_records = {} if args.no_authoritative else load_authoritative_records(Path(args.raw_bibliography))
    url_map = read_json_object(Path(args.url_map))
    authoritative_changes = apply_authoritative_records(articles, authoritative_records)
    url_changes = sync_pdf_urls_from_map(articles, url_map)
    changes = repair_articles(articles)
    candidates = write_ai_candidates(articles, ai_candidates_path)
    ai_changes: list[dict[str, Any]] = []
    ai_results: list[dict[str, Any]] = []
    if args.apply_ai_results:
        ai_changes, ai_results = apply_ai_results_file(
            articles,
            ai_results_path,
            args.ai_min_confidence,
        )
        candidates = write_ai_candidates(articles, ai_candidates_path)
    if args.run_ai_fallback and candidates:
        ai_changes, ai_results = run_ai_fallback(
            articles,
            candidates,
            ai_results_path,
            args.model,
            args.timeout,
            args.ai_min_confidence,
            args.ai_limit,
        )
        candidates = write_ai_candidates(articles, ai_candidates_path)

    print(json.dumps({
        "authoritative_changed": len(authoritative_changes),
        "url_changed": len(url_changes),
        "changed": len(changes),
        "ai_changed": len(ai_changes),
        "ai_results": len(ai_results),
        "ai_candidates": len(candidates),
        "authoritative_changes": authoritative_changes,
        "url_changes": url_changes,
        "changes": changes,
        "ai_changes": ai_changes,
    }, ensure_ascii=False, indent=2))
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
