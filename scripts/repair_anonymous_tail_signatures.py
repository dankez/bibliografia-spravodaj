#!/usr/bin/env python3
"""Repair anonymous article authors from end-of-article signatures.

Issue 1 often contains annual reports where the author is not in the table of
contents.  The signature is usually the last line of the article, sometimes
with a role suffix such as "Igor Balciar, podpredseda".  This script uses the
printed page map plus pdftotext bounding boxes to inspect only the text region
belonging to a specific article, so it does not steal a signature from the next
article on the same page.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from extract_pdf_fulltext import (
    PDF_CACHE_DIR,
    parse_page_range,
    safe_name,
    infer_printed_page_map,
)


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FRONTEND_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
PDF_PAGE_MAP_DIR = BASE_DIR / "data" / "pdf_page_maps"
REPORT_DIR = BASE_DIR / "data" / "author_signature_repairs"
DEFAULT_REPORT_PATH = REPORT_DIR / "anonymous_tail_signatures_dry_run.json"

LETTER_RE = r"A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž"
TITLE_RE = re.compile(r"^(?:doc\.|ing\.|mgr\.|mudr\.|mvdr\.|phdr\.|rndr\.|bc\.|mga\.|phd\.|csc\.)$", re.I)
PREFIX_RE = re.compile(
    r"^\s*(?:napísal|napísala|napísali|autor|autori|text|spracoval|spracovala|spracovali|zostavil|zostavila|zostavili)\s*[:\-]?\s+",
    re.I,
)
INITIAL_NAME_RE = re.compile(
    rf"^(?P<initial>[{LETTER_RE}]\.)\s*(?P<surname>[{LETTER_RE}][{LETTER_RE}'’.-]+)$"
)
SURNAME_INITIAL_RE = re.compile(
    rf"^(?P<surname>[{LETTER_RE}][{LETTER_RE}'’.-]+),\s*(?P<initials>(?:[{LETTER_RE}]\.\s*){{1,3}})$"
)

ROLE_WORDS = {
    "predseda",
    "predsedkyna",
    "podpredseda",
    "podpredsedkyna",
    "veduci",
    "veduca",
    "tajomnik",
    "tajomnicka",
    "hospodar",
    "hospodarka",
    "clen",
    "clenka",
    "spravca",
    "spravkyna",
    "koordinator",
    "koordinatorka",
    "zastupca",
    "zastupkyna",
}
NAME_SUFFIX_RE = re.compile(r"\s+(?:st\.?|ml\.?|starší|mladší)\s*$", re.I)
REJECT_TERMS = {
    "foto",
    "fotografia",
    "obr",
    "tab",
    "spravodaj",
    "organizacne spravy",
    "organizačne spravy",
    "issn",
    "isbn",
    "jaskyna",
    "jaskyne",
    "speleoklub",
    "skupina",
    "klub",
}
TITLE_STOPWORDS = {"a", "v", "vo", "na", "z", "zo", "s", "so", "pre", "do", "the", "and"}
NAME_PARTICLES = {"de", "del", "della", "van", "von"}


@dataclass(frozen=True)
class BboxLine:
    page: int
    order: int
    page_order: int
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    text: str


@dataclass(frozen=True)
class TitleMatch:
    start_index: int
    end_index: int
    score: float
    text: str


@dataclass(frozen=True)
class SignatureCandidate:
    authors: list[str]
    signature_line: str
    source_line: str
    page: int
    order: int
    confidence: float
    reasons: list[str]


class PdfBboxCache:
    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = pdf_path
        self.page_cache: dict[int, list[BboxLine]] = {}

    def page_lines(self, page: int) -> list[BboxLine]:
        if page not in self.page_cache:
            self.page_cache[page] = extract_bbox_page_lines(self.pdf_path, page)
        return self.page_cache[page]

    def lines(self, first_page: int, last_page: int) -> list[BboxLine]:
        combined: list[BboxLine] = []
        for page in range(first_page, last_page + 1):
            for line in self.page_lines(page):
                combined.append(replace(line, order=len(combined)))
        return combined


def read_articles(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected a list in {path}")
    return data


def write_articles(path: Path, articles: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(articles, handle, ensure_ascii=False, indent=2)


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fold_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("ł", "l")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tag_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def float_attr(element: ET.Element, name: str) -> float:
    try:
        return float(element.attrib.get(name, "0"))
    except ValueError:
        return 0.0


def extract_bbox_page_lines(pdf_path: Path, page: int) -> list[BboxLine]:
    cmd = [
        "pdftotext",
        "-bbox-layout",
        "-f",
        str(page),
        "-l",
        str(page),
        str(pdf_path),
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"pdftotext failed for {pdf_path} page {page}")

    xml_text = re.sub(r"<!DOCTYPE[^>]+>", "", result.stdout, count=1)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"Cannot parse pdftotext bbox XML for {pdf_path} page {page}: {exc}") from exc

    lines: list[BboxLine] = []
    for element in root.iter():
        if tag_name(element) != "line":
            continue
        words = [
            clean_space("".join(word.itertext()))
            for word in element
            if tag_name(word) == "word" and clean_space("".join(word.itertext()))
        ]
        text = clean_space(" ".join(words))
        if not text:
            continue
        lines.append(
            BboxLine(
                page=page,
                order=len(lines),
                page_order=len(lines),
                x_min=float_attr(element, "xMin"),
                y_min=float_attr(element, "yMin"),
                x_max=float_attr(element, "xMax"),
                y_max=float_attr(element, "yMax"),
                text=text,
            )
        )
    return lines


def title_tokens(title: str) -> list[str]:
    tokens = [token for token in fold_text(title).split() if token not in TITLE_STOPWORDS]
    return [token for token in tokens if len(token) >= 2]


def title_window_score(title: str, window_text: str) -> float:
    title_norm = fold_text(title)
    window_norm = fold_text(window_text)
    if not title_norm or not window_norm:
        return 0.0
    if title_norm in window_norm:
        return 1.0

    tokens = title_tokens(title)
    if not tokens:
        return 0.0
    window_meaningful_tokens = [token for token in window_norm.split() if token not in TITLE_STOPWORDS]
    if window_norm in title_norm and len(window_meaningful_tokens) >= max(3, math.ceil(len(tokens) * 0.7)):
        return 1.0
    window_tokens = set(window_norm.split())
    matches = sum(1 for token in tokens if token in window_tokens)
    if len(tokens) == 1:
        return 1.0 if matches else 0.0
    return matches / len(tokens)


def title_window_score_strict_heading(title: str, window_text: str) -> float:
    title_tokens_value = title_tokens(title)
    if not title_tokens_value:
        return 0.0

    window_tokens = [token for token in fold_text(window_text).split() if token not in TITLE_STOPWORDS]
    if not window_tokens:
        return 0.0

    title_token_set = set(title_tokens_value)
    window_token_set = set(window_tokens)
    matches = sum(1 for token in title_token_set if token in window_token_set)
    if matches != len(title_token_set):
        return 0.0

    extra_token_count = len(window_tokens) - len(title_tokens_value)
    if len(title_tokens_value) <= 2:
        if extra_token_count > 1:
            return 0.0
    elif extra_token_count > max(2, math.ceil(len(title_tokens_value) * 0.35)):
        return 0.0

    return title_window_score(title, window_text)


def find_title_match(
    lines: list[BboxLine],
    title: str,
    min_index: int = 0,
    *,
    strict_heading: bool = False,
) -> TitleMatch | None:
    best: TitleMatch | None = None
    token_count = max(len(title_tokens(title)), 1)
    min_score = 1.0 if token_count == 1 else 0.72
    for index in range(max(0, min_index), len(lines)):
        preliminary_score = (
            title_window_score_strict_heading(title, lines[index].text)
            if strict_heading
            else title_window_score(title, lines[index].text)
        )
        if preliminary_score <= 0:
            continue
        for width in (1, 2, 3):
            end = index + width
            if end > len(lines):
                continue
            window = " ".join(line.text for line in lines[index:end])
            score = (
                title_window_score_strict_heading(title, window)
                if strict_heading
                else title_window_score(title, window)
            )
            if score < min_score:
                continue
            match = TitleMatch(index, end, score, window)
            if (
                best is None
                or match.start_index < best.start_index
                or (match.start_index == best.start_index and match.score > best.score)
                or (
                    match.start_index == best.start_index
                    and math.isclose(match.score, best.score)
                    and (match.end_index - match.start_index) < (best.end_index - best.start_index)
                )
            ):
                best = match
        if best and best.start_index == index:
            return best
    return best


def find_next_title_match(lines: list[BboxLine], following_articles: list[dict[str, Any]], min_index: int) -> tuple[TitleMatch | None, str]:
    for other in following_articles:
        title = str(other.get("title") or "")
        match = find_title_match(lines, title, min_index=min_index, strict_heading=True)
        if match:
            return match, title
    return None, ""


def has_anonymous_author(article: dict[str, Any]) -> bool:
    authors = [clean_space(str(author)) for author in article.get("authors") or [] if clean_space(str(author))]
    if not authors:
        return True
    return all(fold_text(author) in {"anonymus", "anonymous"} for author in authors)


def article_sort_key(article: dict[str, Any]) -> tuple[int, int, int]:
    start, end = parse_page_range(str(article.get("pages") or ""))
    return (
        start if start is not None else 10**9,
        end if end is not None else start if start is not None else 10**9,
        int(article.get("id") or 0),
    )


def infer_physical_page(printed_page: int, page_map: dict[int, int], max_distance: int = 4) -> int | None:
    if printed_page in page_map:
        return page_map[printed_page]
    nearby = [
        (abs(mapped_printed - printed_page), mapped_physical - mapped_printed)
        for mapped_printed, mapped_physical in page_map.items()
        if abs(mapped_printed - printed_page) <= max_distance
    ]
    if not nearby:
        return None
    distance, offset = sorted(nearby)[0]
    if distance > max_distance:
        return None
    physical = printed_page + offset
    return physical if physical > 0 else None


def resolve_printed_page_range(
    printed_start: int,
    printed_end: int,
    page_map: dict[int, int],
) -> tuple[int | None, int | None, str | None]:
    physical_start = infer_physical_page(printed_start, page_map)
    physical_end = infer_physical_page(printed_end, page_map)
    if physical_start is None or physical_end is None:
        return None, None, "cannot_resolve_physical_pages"
    if physical_end < physical_start:
        physical_end = physical_start
    return physical_start, physical_end, None


def is_footer_or_header(line: BboxLine) -> bool:
    text = clean_space(line.text)
    folded = fold_text(text)
    if not text:
        return True
    if folded in {"spravodaj sss", "organizacne spravy sss"}:
        return True
    if "spravodaj sss" in folded or "organizacne spravy" in folded:
        return True
    if re.fullmatch(r"-?\s*\d{1,4}\s*-?", text):
        return True
    return False


def role_suffix(text: str) -> tuple[str, str | None]:
    match = re.match(r"^(?P<name>.+?),\s*(?P<suffix>[^,]+)$", text)
    if not match:
        return text, None
    suffix = clean_space(match.group("suffix")).strip(".")
    suffix_words = fold_text(suffix).split()
    if suffix_words and suffix_words[0] in ROLE_WORDS:
        return clean_space(match.group("name")), suffix
    return text, None


def signature_text_variants(text: str) -> list[str]:
    text = clean_space(text)
    variants = [text]
    if len(text.split()) > 7:
        match = re.search(r"[.!?]\s+([^.!?]+)$", text)
        if match:
            variants.insert(0, clean_space(match.group(1)))
    return list(dict.fromkeys(variant for variant in variants if variant))


def reject_signature_text(text: str) -> str | None:
    folded = fold_text(text)
    if not text:
        return "empty"
    if any(term in folded for term in REJECT_TERMS):
        return "reject_term"
    if re.search(r"\d", text):
        return "contains_digit"
    if ":" in text:
        return "contains_colon"
    if "(" in text or ")" in text:
        return "contains_parenthesis"
    if any(word.endswith("-") for word in text.split()):
        return "hyphenated_line_break"
    if len(text) > 90:
        return "too_long"
    return None


def split_author_text(text: str) -> list[str]:
    text = clean_space(text)
    text = re.sub(r"\s+(?:a|and|&)\s+", " | ", text, flags=re.I)
    text = re.sub(
        rf",\s+(?=(?:[{LETTER_RE}]\.\s*)?[{LETTER_RE}][{LETTER_RE}'’.-]+(?:\s+[{LETTER_RE}][{LETTER_RE}'’.-]+)?(?:$|\s))",
        " | ",
        text,
    )
    return [clean_space(part) for part in text.split("|") if clean_space(part)]


def normalize_initial(value: str) -> str:
    value = clean_space(value).replace(" ", "")
    pieces = re.findall(rf"[{LETTER_RE}]\.", value)
    return " ".join(piece[0].upper() + "." for piece in pieces)


def is_name_word(word: str) -> bool:
    word = word.strip(".,;")
    if not word:
        return False
    if fold_text(word) in NAME_PARTICLES:
        return True
    if re.fullmatch(rf"[{LETTER_RE}]\.", word):
        return True
    if word.isupper() and len(word) >= 2:
        return False
    parts = [part for part in re.split(r"[-'’]", word) if part]
    return bool(parts) and all(part[:1].isupper() for part in parts)


def format_person_name(raw: str) -> str | None:
    text = clean_space(raw).strip(" ;,")
    if not text:
        return None
    text = clean_space(NAME_SUFFIX_RE.sub("", text))
    words = [word for word in text.split() if not TITLE_RE.match(word.strip())]
    text = clean_space(" ".join(words))
    if not text:
        return None

    match = SURNAME_INITIAL_RE.match(text)
    if match:
        surname = match.group("surname").strip()
        if not is_name_word(surname):
            return None
        return f"{surname}, {normalize_initial(match.group('initials'))}"

    match = INITIAL_NAME_RE.match(text)
    if match:
        surname = match.group("surname").strip()
        if not is_name_word(surname):
            return None
        return f"{surname}, {normalize_initial(match.group('initial'))}"

    text = text.strip(".")
    if not text:
        return None

    if reject_signature_text(text):
        return None

    words = text.split()
    if len(words) < 2 or len(words) > 4:
        return None
    if not all(is_name_word(word) for word in words):
        return None
    if not all(any(char.isalpha() for char in word) for word in words):
        return None
    if sum(1 for word in words if word[:1].isupper()) < 2:
        return None

    surname = words[-1].strip(".,;")
    given = words[:-1]
    initials = []
    for word in given:
        letter = next((char for char in word if char.isalpha()), "")
        if letter:
            initials.append(letter.upper() + ".")
    if not surname or not initials:
        return None
    return f"{surname}, {' '.join(initials)}"


def parse_signature_line(text: str) -> tuple[list[str], str, list[str]] | None:
    for variant in signature_text_variants(text):
        reasons: list[str] = []
        stripped_variant = clean_space(variant)
        without_prefix = clean_space(PREFIX_RE.sub("", stripped_variant))
        candidate = without_prefix.strip(" .;,")
        if without_prefix != stripped_variant:
            reasons.append("signature_prefix")
        candidate, role = role_suffix(candidate)
        if role:
            reasons.append(f"role_suffix:{role}")
        contribution_match = re.match(r"^(?P<main>.+?)\s+s\s+pr[íi]spevkami\b", candidate, flags=re.I)
        if contribution_match:
            candidate = clean_space(contribution_match.group("main")).strip(" .;,")
            reasons.append("with_contributions")
        rejection = reject_signature_text(candidate)
        if rejection:
            continue
        if "," in candidate and not SURNAME_INITIAL_RE.match(candidate):
            continue

        parts = split_author_text(candidate)
        if not 1 <= len(parts) <= 4:
            continue
        authors: list[str] = []
        for part in parts:
            author = format_person_name(part)
            if not author:
                authors = []
                break
            authors.append(author)
        if authors:
            return authors, candidate, reasons
    return None


def parse_group_signature_line(text: str) -> tuple[list[str], str, list[str]] | None:
    candidate = clean_space(text).strip(" .;,")
    folded = fold_text(candidate)
    if not folded.startswith("clenovia "):
        return None
    if len(candidate) > 80 or re.search(r"\d", candidate):
        return None
    if "foto" in folded or "spravodaj" in folded:
        return None
    words = candidate.split()
    folded_words = set(folded.split())
    if any(word.endswith("-") for word in words):
        return None
    if folded_words & {"sa", "su", "boli", "zucastnili", "vykonali", "pracovali", "pokracovali", "navstivili"}:
        return None
    if not 2 <= len(words) <= 7:
        return None
    return [candidate], candidate, ["group_signature"]


def has_role_context_for_signature(content: list[BboxLine], content_index: int, signature_line: str) -> bool:
    target = fold_text(signature_line)
    if not target:
        return False
    role_words = {"predseda", "predsedu", "predsedkyna", "predsednicka", "veduci", "veduceho"}
    for line in content[max(0, content_index - 160) : content_index]:
        folded = fold_text(line.text)
        if target in folded and role_words.intersection(folded.split()):
            return True
    return False


def find_tail_signature(region_lines: list[BboxLine], tail_line_count: int = 42) -> SignatureCandidate | None:
    content = [line for line in region_lines if not is_footer_or_header(line)]
    tail_start = max(0, len(content) - tail_line_count)
    candidate_indexes = set(range(tail_start, len(content)))
    for index, line in enumerate(content[:tail_start]):
        if line.y_min >= 560:
            candidate_indexes.add(index)
    candidates: list[SignatureCandidate] = []
    for content_index in sorted(candidate_indexes, reverse=True):
        line = content[content_index]
        distance_from_end = len(content) - 1 - content_index
        source_texts = []
        if clean_space(line.text).rstrip().endswith(",") and content_index + 1 < len(content):
            source_texts.append(f"{line.text} {content[content_index + 1].text}")
        source_texts.append(line.text)

        parsed: tuple[list[str], str, list[str]] | None = None
        source_text = line.text
        for possible_source in source_texts:
            parsed = parse_group_signature_line(possible_source) or parse_signature_line(possible_source)
            if parsed:
                source_text = possible_source
                break
        if not parsed:
            continue
        authors, signature_line, reasons = parsed
        candidate_reasons = list(reasons)
        confidence = 0.68
        if any(reason.startswith("role_suffix:") for reason in candidate_reasons):
            confidence += 0.16
        if "signature_prefix" in candidate_reasons:
            confidence += 0.12
        if "with_contributions" in candidate_reasons:
            confidence += 0.12
        if "group_signature" in candidate_reasons:
            confidence += 0.18
        if not candidate_reasons and has_role_context_for_signature(content, content_index, signature_line):
            confidence += 0.16
            candidate_reasons.append("role_context")
        if not candidate_reasons and clean_space(source_text).strip(" .;,") == signature_line:
            if distance_from_end == 0:
                confidence += 0.12
            elif distance_from_end == 1:
                confidence += 0.08
            elif line.y_min >= 560:
                confidence += 0.16
        if distance_from_end <= 3:
            confidence += 0.08
        if len(authors) <= 2:
            confidence += 0.04
        confidence = min(confidence, 0.98)
        candidates.append(
            SignatureCandidate(
                authors=authors,
                signature_line=signature_line,
                source_line=clean_space(source_text),
                page=line.page,
                order=line.order,
                confidence=confidence,
                reasons=candidate_reasons or ["tail_name_pattern"],
            )
        )
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item.confidence, -item.order))[0]


def pdf_path_for_article(article: dict[str, Any]) -> Path | None:
    pdf_cache = article.get("pdf_cache")
    if pdf_cache:
        path = Path(str(pdf_cache))
        if not path.is_absolute():
            path = BASE_DIR / path
        if path.exists():
            return path

    pdf_url = str(article.get("pdf_url") or "")
    if not pdf_url:
        return None
    cache_path = PDF_CACHE_DIR / safe_name(pdf_url)
    if cache_path.exists():
        return cache_path

    filename = Path(pdf_url.split("?", 1)[0]).name
    matches = sorted(PDF_CACHE_DIR.glob(f"*_{filename}"))
    return matches[0] if matches else None


def issue_matches(article: dict[str, Any], year: int | None, issue: str | None, all_issues: bool) -> bool:
    if year is not None and article.get("year") != year:
        return False
    if not all_issues and issue is not None and str(article.get("issue") or "") != str(issue):
        return False
    return True


def build_article_region(
    article: dict[str, Any],
    issue_articles: list[dict[str, Any]],
    page_map: dict[int, int],
    pdf_cache: PdfBboxCache,
) -> tuple[list[BboxLine], dict[str, Any]]:
    printed_start, printed_end = parse_page_range(str(article.get("pages") or ""))
    if printed_start is None or printed_end is None:
        return [], {"skip_reason": "missing_printed_pages"}

    ordered_articles = sorted(issue_articles, key=article_sort_key)
    following_articles = [
        other
        for other in ordered_articles
        if article_sort_key(other) > article_sort_key(article)
    ]
    next_printed_start: int | None = None
    if following_articles:
        next_printed_start, _next_printed_end = parse_page_range(str(following_articles[0].get("pages") or ""))
    search_printed_end = max(
        printed_end,
        next_printed_start if next_printed_start is not None else printed_end,
    )

    physical_start, physical_end, error = resolve_printed_page_range(printed_start, search_printed_end, page_map)
    if error or physical_start is None or physical_end is None:
        return [], {"skip_reason": error or "cannot_resolve_physical_pages"}

    lines = pdf_cache.lines(physical_start, physical_end)
    title_match = find_title_match(lines, str(article.get("title") or ""))
    search_after = title_match.end_index if title_match else 0

    next_match, next_title = find_next_title_match(lines, following_articles, search_after)

    start_index = title_match.end_index if title_match else 0
    end_index = next_match.start_index if next_match else len(lines)
    if end_index < start_index:
        end_index = len(lines)

    metadata = {
        "printed_pages": [printed_start, printed_end],
        "search_printed_pages": [printed_start, search_printed_end],
        "physical_pages": [physical_start, physical_end],
        "title_match": {
            "found": bool(title_match),
            "score": round(title_match.score, 3) if title_match else 0,
            "text": title_match.text if title_match else "",
        },
        "next_title": next_title,
        "next_title_match": {
            "found": bool(next_match),
            "score": round(next_match.score, 3) if next_match else 0,
            "text": next_match.text if next_match else "",
        },
    }
    return lines[start_index:end_index], metadata


def build_gemma_prompt(article: dict[str, Any], candidate: SignatureCandidate, context_lines: list[BboxLine], meta: dict[str, Any]) -> str:
    tail = "\n".join(
        f"[page {line.page} line {line.page_order}] {line.text}"
        for line in context_lines[-22:]
        if not is_footer_or_header(line)
    )
    return (
        "Si konzervatívny bibliograf pre časopis Spravodaj SSS. "
        "Over, či kandidátsky podpis patrí k zadanému článku, nie k nasledujúcemu článku. "
        "Ignoruj funkcie ako predseda/podpredseda a ignoruj Foto popisy. "
        "Nevymýšľaj autora mimo dodaného výrezu. Vráť iba JSON.\n\n"
        f"Článok: {article.get('title')}\n"
        f"Nasledujúci titulok: {meta.get('next_title') or '(nezistený)'}\n"
        f"Kandidátsky podpis: {candidate.signature_line}\n"
        f"Kandidátski autori: {', '.join(candidate.authors)}\n\n"
        f"Koniec výrezu článku:\n{tail}\n\n"
        'JSON schéma: {"accept": true|false, "authors": ["Priezvisko, I."], '
        '"signature_line": "text", "confidence": 0.0, "reason": "stručne"}'
    )


def build_gemma_extract_prompt(article: dict[str, Any], context_lines: list[BboxLine], meta: dict[str, Any]) -> str:
    tail = "\n".join(
        f"[page {line.page} line {line.page_order}] {line.text}"
        for line in context_lines[-44:]
        if not is_footer_or_header(line)
    )
    return (
        "Si konzervatívny bibliograf pre časopis Spravodaj SSS. "
        "V zadanom výreze nájdi autora článku podľa podpisu na konci článku. "
        "Podpis môže byť oddelený prázdnym riadkom a môže začínať slovami Napísal/Napísali/Zostavil. "
        "Ak sú dvaja autori, vráť ich ako dva samostatné prvky poľa authors. "
        "Ignoruj funkcie ako predseda, podpredseda, vedúci, tajomník. "
        "Ignoruj Foto popisy, mená osôb v texte, mená v popisoch fotografií a autorov nasledujúceho článku. "
        "Ak podpis autora vo výreze nevidíš, vráť accept=false. Nevymýšľaj. Vráť iba JSON.\n\n"
        f"Článok: {article.get('title')}\n"
        f"Nasledujúci titulok: {meta.get('next_title') or '(nezistený)'}\n\n"
        f"Koniec výrezu článku:\n{tail}\n\n"
        'JSON schéma: {"accept": true|false, "authors": ["Priezvisko, I."], '
        '"signature_line": "presný riadok podpisu", "confidence": 0.0, "reason": "stručne"}'
    )


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def confirm_with_gemma(prompt: str, model: str, ollama_url: str, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        ollama_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"accept": False, "error": f"ollama_error: {exc}"}
    content = ((body.get("message") or {}).get("content") or body.get("response") or "").strip()
    result = extract_json_object(content)
    if not result:
        return {"accept": False, "error": "gemma_parse_error", "raw": content[:1000]}
    return result


def gemma_confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(parsed):
        return 0.0
    return max(0.0, min(parsed, 1.0))


def normalize_gemma_authors(value: Any) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, list):
        raw_items = [clean_space(str(item)) for item in value if clean_space(str(item))]
    else:
        text = clean_space(str(value or ""))
        if text:
            raw_items = [text]

    authors: list[str] = []
    for item in raw_items:
        parts = [clean_space(part) for part in re.split(r"\s*;\s*|\s+\ba\b\s+", item) if clean_space(part)]
        if len(parts) <= 1:
            parsed = parse_signature_line(item)
            if parsed:
                authors.extend(parsed[0])
                continue
        for part in parts:
            part = clean_space(part)
            if not part:
                continue
            author = format_person_name(part)
            if author:
                authors.append(author)

    unique: list[str] = []
    for author in authors:
        if author not in unique:
            unique.append(author)
    return unique[:4]


def repair_candidates(
    articles: list[dict[str, Any]],
    *,
    year: int | None,
    issue: str | None,
    all_issues: bool,
    article_ids: set[int] | None,
    limit: int | None,
    use_gemma: bool,
    gemma_fallback: bool,
    gemma_model: str,
    gemma_limit: int,
    gemma_timeout: int,
    ollama_url: str,
) -> dict[str, Any]:
    articles_by_pdf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        pdf_url = str(article.get("pdf_url") or "")
        if pdf_url:
            articles_by_pdf[pdf_url].append(article)

    targets = [
        article
        for article in articles
        if has_anonymous_author(article) and issue_matches(article, year, issue, all_issues)
    ]
    if article_ids:
        targets = [article for article in targets if int(article.get("id") or 0) in article_ids]
    targets = sorted(targets, key=lambda item: (str(item.get("pdf_url") or ""), article_sort_key(item)))
    if limit is not None:
        targets = targets[:limit]

    pdf_caches: dict[Path, PdfBboxCache] = {}
    page_maps: dict[str, dict[int, int]] = {}
    changes: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    gemma_calls = 0

    for article in targets:
        pdf_url = str(article.get("pdf_url") or "")
        pdf_path = pdf_path_for_article(article)
        if pdf_path is None:
            skipped.append({"id": article.get("id"), "title": article.get("title"), "reason": "missing_pdf_cache"})
            continue

        if pdf_url not in page_maps:
            PDF_PAGE_MAP_DIR.mkdir(parents=True, exist_ok=True)
            page_map_cache = PDF_PAGE_MAP_DIR / f"{safe_name(pdf_url)}.json"
            page_maps[pdf_url] = infer_printed_page_map(pdf_path, page_map_cache)
            if not page_maps[pdf_url]:
                page_maps[pdf_url] = infer_printed_page_map(pdf_path, page_map_cache, force=True)
        printed_start, _printed_end = parse_page_range(str(article.get("pages") or ""))
        if printed_start is not None and printed_start not in page_maps[pdf_url]:
            page_maps[pdf_url] = infer_printed_page_map(
                pdf_path,
                PDF_PAGE_MAP_DIR / f"{safe_name(pdf_url)}.json",
                force=True,
            )
        if pdf_path not in pdf_caches:
            pdf_caches[pdf_path] = PdfBboxCache(pdf_path)

        issue_articles = [
            other
            for other in articles_by_pdf.get(pdf_url, [])
            if str(other.get("issue") or "") == str(article.get("issue") or "")
            and other.get("year") == article.get("year")
        ]
        try:
            region, meta = build_article_region(article, issue_articles, page_maps[pdf_url], pdf_caches[pdf_path])
        except Exception as exc:
            skipped.append({"id": article.get("id"), "title": article.get("title"), "reason": f"region_error: {exc}"})
            continue
        if not region:
            skipped.append({"id": article.get("id"), "title": article.get("title"), **meta})
            continue

        candidate = find_tail_signature(region)
        if not candidate:
            gemma_result: dict[str, Any] | None = None
            gemma_authors: list[str] = []
            if gemma_fallback and gemma_calls < gemma_limit:
                prompt = build_gemma_extract_prompt(article, region, meta)
                gemma_result = confirm_with_gemma(prompt, gemma_model, ollama_url, gemma_timeout)
                gemma_calls += 1
                if gemma_result.get("accept") is not False:
                    gemma_authors = normalize_gemma_authors(gemma_result.get("authors"))
            if gemma_authors:
                confidence = gemma_confidence(gemma_result.get("confidence")) if gemma_result else 0.0
                changes.append(
                    {
                        "id": article.get("id"),
                        "title": article.get("title"),
                        "year": article.get("year"),
                        "issue": article.get("issue"),
                        "pages": article.get("pages"),
                        "old_authors": article.get("authors") or [],
                        "new_authors": gemma_authors,
                        "confidence": round(max(confidence, 0.7), 3),
                        "signature_line": clean_space(str(gemma_result.get("signature_line") or "")) if gemma_result else "",
                        "source_line": clean_space(str(gemma_result.get("signature_line") or "")) if gemma_result else "",
                        "source_page": region[-1].page if region else None,
                        "reasons": ["gemma_tail_signature"],
                        "context_tail": [line.text for line in region[-16:] if not is_footer_or_header(line)],
                        "gemma": gemma_result,
                        **meta,
                    }
                )
                continue
            review.append(
                {
                    "id": article.get("id"),
                    "title": article.get("title"),
                    "reason": "no_tail_signature",
                    "gemma": gemma_result,
                    "tail": [line.text for line in region[-12:] if not is_footer_or_header(line)],
                    **meta,
                }
            )
            continue

        gemma_result: dict[str, Any] | None = None
        if use_gemma and gemma_calls < gemma_limit:
            prompt = build_gemma_prompt(article, candidate, region, meta)
            gemma_result = confirm_with_gemma(prompt, gemma_model, ollama_url, gemma_timeout)
            gemma_calls += 1
            if gemma_result.get("accept") is False:
                review.append(
                    {
                        "id": article.get("id"),
                        "title": article.get("title"),
                        "reason": "gemma_rejected",
                        "candidate_authors": candidate.authors,
                        "signature_line": candidate.signature_line,
                        "gemma": gemma_result,
                        **meta,
                    }
                )
                continue

        new_authors = candidate.authors
        if gemma_result and isinstance(gemma_result.get("authors"), list):
            gemma_authors = normalize_gemma_authors(gemma_result.get("authors"))
            if gemma_authors:
                new_authors = gemma_authors

        changes.append(
            {
                "id": article.get("id"),
                "title": article.get("title"),
                "year": article.get("year"),
                "issue": article.get("issue"),
                "pages": article.get("pages"),
                "old_authors": article.get("authors") or [],
                "new_authors": new_authors,
                "confidence": round(float(candidate.confidence), 3),
                "signature_line": candidate.signature_line,
                "source_line": candidate.source_line,
                "source_page": candidate.page,
                "reasons": candidate.reasons,
                "context_tail": [line.text for line in region[-12:] if not is_footer_or_header(line)],
                "gemma": gemma_result,
                **meta,
            }
        )

    return {
        "scanned": len(targets),
        "changed": len(changes),
        "review": len(review),
        "skipped": len(skipped),
        "gemma_calls": gemma_calls,
        "changes": changes,
        "review_items": review,
        "skipped_items": skipped,
    }


def apply_changes(articles: list[dict[str, Any]], changes: list[dict[str, Any]], min_confidence: float) -> int:
    by_id = {article.get("id"): article for article in articles}
    applied = 0
    for change in changes:
        if float(change.get("confidence") or 0) < min_confidence:
            continue
        article = by_id.get(change.get("id"))
        if not article:
            continue
        new_authors = [clean_space(str(author)) for author in change.get("new_authors") or [] if clean_space(str(author))]
        if not new_authors:
            continue
        article["authors"] = new_authors
        article["author_source"] = "tail_signature_repair"
        article["author_confidence"] = float(change.get("confidence") or 0)
        applied += 1
    return applied


def sync_frontend(frontend_path: Path, changes: list[dict[str, Any]], min_confidence: float) -> int:
    if not frontend_path.exists():
        return 0
    frontend_articles = read_articles(frontend_path)
    applied = apply_changes(frontend_articles, changes, min_confidence)
    if applied:
        write_articles(frontend_path, frontend_articles)
    return applied


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair anonymous authors from article tail signatures.")
    parser.add_argument("--articles", default=str(ARTICLES_PATH), help="Canonical articles JSON.")
    parser.add_argument("--frontend", default=str(FRONTEND_ARTICLES_PATH), help="Frontend articles JSON to sync on --apply.")
    parser.add_argument("--year", type=int, help="Restrict to one year.")
    parser.add_argument("--issue", default="1", help="Restrict to issue number, default 1.")
    parser.add_argument("--all-issues", action="store_true", help="Ignore --issue and scan all issues.")
    parser.add_argument("--article-id", type=int, action="append", help="Restrict scan/apply to one article id. Repeatable.")
    parser.add_argument("--limit", type=positive_int, help="Maximum anonymous records to scan.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="Dry-run/apply report JSON path.")
    parser.add_argument("--apply", action="store_true", help="Write high-confidence author repairs to article JSON files.")
    parser.add_argument("--min-confidence", type=float, default=0.88, help="Minimum confidence for --apply.")
    parser.add_argument("--use-gemma", action="store_true", help="Ask local Gemma to confirm deterministic candidates.")
    parser.add_argument("--gemma-fallback", action="store_true", help="Ask local Gemma to extract authors when deterministic parsing finds no tail signature.")
    parser.add_argument("--gemma-model", default="gemma4:e2b-it-qat")
    parser.add_argument("--gemma-limit", type=int, default=20, help="Maximum Gemma confirmation calls.")
    parser.add_argument("--gemma-timeout", type=int, default=120)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()

    articles_path = Path(args.articles)
    frontend_path = Path(args.frontend)
    articles = read_articles(articles_path)
    report = repair_candidates(
        articles,
        year=args.year,
        issue=str(args.issue) if args.issue is not None else None,
        all_issues=args.all_issues,
        article_ids=set(args.article_id or []),
        limit=args.limit,
        use_gemma=args.use_gemma,
        gemma_fallback=args.gemma_fallback,
        gemma_model=args.gemma_model,
        gemma_limit=max(0, args.gemma_limit),
        gemma_timeout=args.gemma_timeout,
        ollama_url=args.ollama_url,
    )

    applied = 0
    frontend_applied = 0
    if args.apply:
        applied = apply_changes(articles, report["changes"], args.min_confidence)
        if applied:
            write_articles(articles_path, articles)
            frontend_applied = sync_frontend(frontend_path, report["changes"], args.min_confidence)

    report["applied"] = applied
    report["frontend_applied"] = frontend_applied
    report["mode"] = "apply" if args.apply else "dry_run"
    report["filters"] = {"year": args.year, "issue": None if args.all_issues else args.issue}
    report["recommended_apply_count"] = sum(
        1 for change in report["changes"] if float(change.get("confidence") or 0) >= args.min_confidence
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "mode": report["mode"],
        "scanned": report["scanned"],
        "changed": report["changed"],
        "review": report["review"],
        "skipped": report["skipped"],
        "applied": applied,
        "frontend_applied": frontend_applied,
        "recommended_apply_count": report["recommended_apply_count"],
        "report": str(report_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
