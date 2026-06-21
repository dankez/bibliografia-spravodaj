#!/usr/bin/env python3
"""Import article records from all journal issue PDFs listed in the source manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import extract_pdf_fulltext as fulltext
import journal_sources
from codex_ai_backend import CodexAuthError, run_codex_json
from generate_missing_abstracts import safe_title_abstract


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = BASE_DIR / "data" / "journal_sources_manifest.json"
DEFAULT_ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
DEFAULT_FRONTEND_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
DEFAULT_STATE_PATH = BASE_DIR / "data" / "journal_issue_import_state.json"
DEFAULT_EVENTS_PATH = BASE_DIR / "data" / "journal_issue_import_events.jsonl"
CREATED_BY = "codex_journal_issue_import"
DEFAULT_JOURNALS = {"aragonit", "slovensky_kras"}
DEFAULT_MODEL = "gpt-5.5"

ARTICLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "authors": {"type": "array", "items": {"type": "string"}},
                    "pages": {"type": "string"},
                    "extras": {"type": "array", "items": {"type": "string"}},
                    "abstract": {"type": "string"},
                    "caves": {"type": "array", "items": {"type": "string"}},
                    "has_map_plan": {"type": "boolean"},
                },
                "required": [
                    "title",
                    "authors",
                    "pages",
                    "extras",
                    "abstract",
                    "caves",
                    "has_map_plan",
                ],
            },
        }
    },
    "required": ["articles"],
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_issue_key(item: dict[str, Any]) -> str:
    return f"{item.get('journal_id')}:{item.get('issue_key')}"


def existing_source_issue_keys(articles: list[dict[str, Any]]) -> set[str]:
    return {
        str(article.get("source_issue_key"))
        for article in articles
        if article.get("source_issue_key")
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_issue_key_file(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return set()
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            values = payload.get("with_toc") or payload.get("issue_keys") or payload.get("keys") or []
        else:
            values = payload
        return {str(value).strip() for value in values if str(value).strip()}
    return {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": utc_now(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def write_state(path: Path, state: dict[str, Any]) -> None:
    write_json(path, {"updated_at": utc_now(), **state})


def select_manifest_items(
    items: list[dict[str, Any]],
    *,
    existing_keys: set[str],
    journals: set[str],
    include_issue_keys: set[str] | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("journal_id") or "") not in journals:
            continue
        key = source_issue_key(item)
        issue_key = str(item.get("issue_key") or "")
        if include_issue_keys and key not in include_issue_keys and issue_key not in include_issue_keys:
            continue
        if not force and key in existing_keys:
            continue
        selected.append(item)
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


def time_budget_exhausted(
    *,
    start_monotonic: float,
    now_monotonic: float,
    max_seconds: int | None,
    completed: int,
) -> bool:
    return bool(max_seconds and completed > 0 and now_monotonic - start_monotonic >= max_seconds)


def normalize_pages(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", "", text)
    return text


def parse_page_range(value: Any) -> tuple[int | None, int | None]:
    text = normalize_pages(value)
    match = re.match(r"^(\d{1,4})(?:-(\d{1,4}))?", text)
    if not match:
        return None, None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if end < start:
        end = start
    return start, end


def page_label(start: int | None, end: int | None) -> str:
    if start is None:
        return ""
    if end is None or end <= start:
        return str(start)
    return f"{start}-{end}"


def infer_end_pages(parsed_articles: list[dict[str, Any]]) -> list[tuple[int | None, int | None]]:
    starts: list[int | None] = []
    explicit_ends: list[int | None] = []
    for article in parsed_articles:
        start, end = parse_page_range(article.get("pages"))
        starts.append(start)
        explicit_ends.append(end if start != end else None)

    ranges: list[tuple[int | None, int | None]] = []
    for index, start in enumerate(starts):
        if start is None:
            ranges.append((None, None))
            continue
        explicit_end = explicit_ends[index]
        if explicit_end is not None:
            ranges.append((start, explicit_end))
            continue
        next_start = next((value for value in starts[index + 1 :] if value is not None and value > start), None)
        end = next_start - 1 if next_start else start
        ranges.append((start, end))
    return ranges


def printed_to_physical_page(
    printed_page: int | None,
    page_map: dict[int, int],
    item: dict[str, Any],
) -> int | None:
    if printed_page is None:
        return None
    if printed_page in page_map:
        return page_map[printed_page]
    if page_map:
        nearest = max((page for page in page_map if page <= printed_page), default=None)
        if nearest is not None:
            return page_map[nearest] + (printed_page - nearest)
        nearest = min((page for page in page_map if page >= printed_page), default=None)
        if nearest is not None:
            return max(1, page_map[nearest] - (nearest - printed_page))
    try:
        offset = int(item.get("pdf_page_offset") or 0)
    except (TypeError, ValueError):
        offset = 0
    return max(1, printed_page + offset)


def looks_like_map_plan(article: dict[str, Any]) -> bool:
    blob = normalize_spaces(
        " ".join(
            [
                article.get("title") or "",
                article.get("abstract") or "",
                " ".join(str(item) for item in article.get("extras") or []),
            ]
        )
    ).casefold()
    if re.search(r"\bplán\s+(?:práce|činnosti|podujatia|zasadnutia)\b", blob):
        return False
    return bool(
        article.get("has_map_plan")
        or re.search(r"\bmap[ay]?\b|\bpl\.\s*j\.|\bpôdorys\b|\bpodorys\b|\bplán\s+jask", blob)
    )


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = normalize_spaces(value)
        key = journal_sources.normalize_ascii(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def build_article_records(
    item: dict[str, Any],
    parsed_articles: list[dict[str, Any]],
    *,
    start_id: int,
    printed_to_physical: dict[int, int],
    created_at: str,
    model: str = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    ranges = infer_end_pages(parsed_articles)
    next_id = start_id
    issue_key = source_issue_key(item)

    for parsed, (printed_start, printed_end) in zip(parsed_articles, ranges, strict=True):
        title = normalize_spaces(parsed.get("title"))
        if not title:
            continue

        physical_start = printed_to_physical_page(printed_start, printed_to_physical, item)
        physical_end = printed_to_physical_page(printed_end, printed_to_physical, item)
        if physical_start is not None and physical_end is not None and physical_end < physical_start:
            physical_end = physical_start

        authors = unique_strings(parsed.get("authors") or []) or ["Anonymus"]
        caves = unique_strings(parsed.get("caves") or [])
        extras = unique_strings(parsed.get("extras") or [])
        abstract = normalize_spaces(parsed.get("abstract"))
        abstract_source = "toc_ai" if abstract else "title_fallback"
        article = {
            "id": next_id,
            "authors": authors,
            "title": title,
            "pages": page_label(printed_start, printed_end),
            "extras": extras,
            "year": item.get("year"),
            "volume": str(item.get("volume") or ""),
            "issue": str(item.get("issue") or ""),
            "abstract": abstract,
            "abstract_source": abstract_source,
            "abstract_generated_by": model if abstract else "title_fallback",
            "abstract_generated_at": created_at,
            "pdf_url": item.get("pdf_url") or "",
            "journal_id": item.get("journal_id") or "",
            "journal_title": item.get("journal_title") or "",
            "journal_short_title": item.get("journal_short_title") or "",
            "source_issue_key": issue_key,
            "source_manifest_item": item.get("issue_key") or "",
            "created_by": CREATED_BY,
            "created_at": created_at,
            "pdf_page_start": physical_start,
            "pdf_page_end": physical_end,
            "pdf_page_offset": 0,
            "caves": caves,
            "caves_verified": bool(caves),
            "tags": unique_strings([item.get("journal_short_title") or item.get("journal_title"), "Speleológia"]),
            "groups": [],
            "wikidata": [],
        }
        if not article["abstract"]:
            article["abstract"] = safe_title_abstract(article)
        if article["abstract_source"] == "title_fallback" and article["abstract"]:
            article["abstract_generated_at"] = created_at

        if looks_like_map_plan({**parsed, **article}):
            article["has_map_plan"] = True
            if physical_start is not None:
                article["map_plan_pages"] = [physical_start]
            article["tags"] = unique_strings([*article["tags"], "mapa/plán"])

        records.append(article)
        next_id += 1
    return records


def first_content_slice(text: str, markers: list[str], max_chars: int) -> str:
    folded = text.casefold()
    indexes = [folded.find(marker.casefold()) for marker in markers]
    indexes = [index for index in indexes if index >= 0]
    start = min(indexes) if indexes else 0
    return text[start : start + max_chars]


TOC_HEADING_RE = re.compile(r"^(?:OBSAH|CONTENTS|INHALT|TABLE\s+OF\s+CONTENTS)(?:\b|$)", re.I)
SLOVAK_TOC_HEADING_RE = re.compile(r"^OBSAH(?:\b|$)", re.I)
ENGLISH_TOC_HEADING_RE = re.compile(r"^(?:CONTENTS|TABLE\s+OF\s+CONTENTS)(?:\b|$)", re.I)
GERMAN_TOC_HEADING_RE = re.compile(r"^INHALT(?:\b|$)", re.I)
TOC_LINE_END_RE = re.compile(r".{8,}\s(?:\.{2,}\s*)?\d{1,4}\s*$")
TOC_LIKE_SCORE_THRESHOLD = 8


def has_toc_marker(text: str) -> bool:
    return toc_marker_rank(text) < 99


def compact_heading(value: str) -> str:
    return re.sub(r"[^A-ZÁÄČĎÉÍĹĽŇÓÔÖŔŘŠŤÚÜÝŽ]", "", value.upper())


def toc_marker_rank(text: str) -> int:
    """Rank a page/section by TOC language; Slovak TOC is preferred."""
    for line in str(text or "").splitlines():
        normalized = normalize_spaces(line)
        if not normalized or len(normalized) > 100:
            continue
        compact = compact_heading(normalized)
        if compact == "OBSAH":
            return 0
        if compact in {"CONTENTS", "TABLEOFCONTENTS"}:
            return 1
        if compact == "INHALT":
            return 2
        if SLOVAK_TOC_HEADING_RE.search(normalized):
            return 0
        if ENGLISH_TOC_HEADING_RE.search(normalized):
            return 1
        if GERMAN_TOC_HEADING_RE.search(normalized):
            return 2
        if TOC_HEADING_RE.search(normalized):
            return 3
    return 99


def toc_like_score(text: str) -> int:
    score = 0
    for line in str(text or "").splitlines():
        compact = normalize_spaces(line)
        if len(compact) < 8:
            continue
        if TOC_LINE_END_RE.match(compact):
            score += 1
        if ":" in compact and re.search(r"\d{1,4}\s*$", compact):
            score += 2
    return score


def has_toc_context(text: str) -> bool:
    return has_toc_marker(text) or toc_like_score(text) >= TOC_LIKE_SCORE_THRESHOLD


def is_edge_page(page: int, page_count: int, fallback_pages: int) -> bool:
    return page <= fallback_pages + 2 or page >= max(1, page_count - fallback_pages - 2)


def select_toc_candidate_pages(
    page_texts: list[tuple[int, str]],
    *,
    fallback_pages: int,
    max_pages: int = 18,
) -> list[int]:
    if not page_texts:
        return []
    page_count = max(page for page, _ in page_texts)
    text_by_page = {page: text for page, text in page_texts}
    page_scores = {page: toc_like_score(text) for page, text in page_texts}
    hit_pages = {
        page
        for page, text in page_texts
        if has_toc_marker(text) or page_scores.get(page, 0) >= TOC_LIKE_SCORE_THRESHOLD
    }
    if not hit_pages:
        return list(range(1, min(page_count, fallback_pages) + 1))

    candidates: set[int] = set()
    for page in hit_pages:
        for candidate in range(page - 1, page + 2):
            if 1 <= candidate <= page_count:
                candidates.add(candidate)

    def sort_key(page: int) -> tuple[int, int, int, int, int, int]:
        text = text_by_page.get(page, "")
        return (
            0 if is_edge_page(page, page_count, fallback_pages) else 1,
            toc_marker_rank(text),
            -page_scores.get(page, 0),
            0 if page in hit_pages else 1,
            min(abs(page - hit) for hit in hit_pages),
            page,
        )

    return sorted(sorted(candidates, key=sort_key)[:max_pages])


def requires_toc_marker(item: dict[str, Any]) -> bool:
    return str(item.get("journal_id") or "") == "slovensky_kras"


def fetch_detail_text(item: dict[str, Any]) -> str:
    detail_url = str(item.get("detail_url") or "").strip()
    if not detail_url:
        return ""
    html = journal_sources.requests_fetch_text(detail_url)
    text = journal_sources.extract_text(html)
    return first_content_slice(text, ["Obsah / Contents", "Obsah čísla", "OBSAH"], 14000)


def extract_pdf_toc_text_from_page_provider(
    *,
    page_count: int,
    fallback_pages: int,
    page_text: Any,
    max_pages: int = 18,
) -> str:
    cache: dict[int, str] = {}

    def cached_text(page: int) -> str:
        if page not in cache:
            cache[page] = page_text(page)
        return cache[page]

    all_page_texts = [(page, cached_text(page)) for page in range(1, page_count + 1)]
    selected_pages = select_toc_candidate_pages(
        all_page_texts,
        fallback_pages=fallback_pages,
        max_pages=max_pages,
    )

    def output_key(page: int) -> tuple[int, int, int, int]:
        return (
            toc_marker_rank(cached_text(page)),
            0 if is_edge_page(page, page_count, fallback_pages) else 1,
            -toc_like_score(cached_text(page)),
            page,
        )

    parts: list[str] = []
    for page in sorted(selected_pages, key=output_key):
        text = cached_text(page).strip()
        if text:
            parts.append(f"PDF PAGE {page}\n{text}")
    return "\n\n".join(parts)


def extract_pdf_toc_text(pdf_path: Path, toc_pages: int) -> str:
    page_count = fulltext.pdf_page_count(pdf_path)
    return extract_pdf_toc_text_from_page_provider(
        page_count=page_count,
        fallback_pages=toc_pages,
        page_text=lambda page: fulltext.pdftotext(pdf_path, page, page),
    )


def extended_printed_page_number(text: str) -> int | None:
    base = fulltext.infer_printed_page_number(text)
    if base is not None:
        return base
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = lines[:10] + list(reversed(lines[-12:]))
    patterns = [
        re.compile(r"\bAragonit\s+\d+(?:\s*[/_-]\s*\d+(?:-\d+)?)?\s+\d{4}\s+(\d{1,4})\b", re.I),
        re.compile(r"\b(\d{1,4})\s+Aragonit\s+\d+(?:\s*[/_-]\s*\d+(?:-\d+)?)?\s+\d{4}\b", re.I),
        re.compile(r"\bSLOVENSKÝ\s+KRAS\s+\d+(?:\s*/\s*\d+)?\s+(\d{1,4})\s*[-–]\s*\d{1,4}\b", re.I),
    ]
    for line in candidates:
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                return int(match.group(1))
    return None


def infer_printed_to_physical_page_map(pdf_path: Path, cache_path: Path, force: bool = False) -> dict[int, int]:
    if cache_path.exists() and not force:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return {int(key): int(value) for key, value in cached.items()}
        except Exception:
            pass

    page_map: dict[int, int] = {}
    page_count = fulltext.pdf_page_count(pdf_path)
    for physical_page in range(1, page_count + 1):
        try:
            page_text = fulltext.pdftotext(pdf_path, physical_page, physical_page)
        except Exception:
            continue
        printed = extended_printed_page_number(page_text)
        if printed is not None:
            page_map.setdefault(printed, physical_page)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({str(key): value for key, value in sorted(page_map.items())}, indent=2),
        encoding="utf-8",
    )
    return page_map


def download_issue_pdf(item: dict[str, Any], force: bool = False) -> Path:
    url = str(item.get("pdf_url") or "").strip()
    if not url:
        raise RuntimeError("Issue has no pdf_url")
    fulltext.PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = fulltext.PDF_CACHE_DIR / fulltext.safe_name(url)
    if not fulltext.download_pdf(url, pdf_path, force=force):
        raise RuntimeError(f"PDF download failed: {url}")
    return pdf_path


def build_issue_context(item: dict[str, Any], pdf_path: Path, toc_pages: int) -> str:
    parts: list[str] = []
    try:
        detail_text = fetch_detail_text(item)
    except Exception as exc:
        detail_text = ""
        parts.append(f"DETAIL HTML ERROR: {exc}")
    if detail_text:
        parts.append("WEB DETAIL TEXT:\n" + detail_text)

    pdf_text = extract_pdf_toc_text(pdf_path, toc_pages)
    if pdf_text:
        parts.append("PDF FIRST PAGES TEXT:\n" + pdf_text[:22000])
    context = "\n\n".join(parts).strip()
    if requires_toc_marker(item) and not has_toc_context(context):
        raise RuntimeError("No TOC context found; requires full-text article segmentation")
    return context


def build_toc_prompt(item: dict[str, Any], context: str) -> str:
    return (
        "Si konzervatívny bibliograf pre slovenské speleologické časopisy. "
        "Z dodaného textu obsahu čísla extrahuj iba samostatné články/príspevky. "
        "Nevkladaj redakčné údaje, tiráž, obálku, zoznam redakčnej rady ani navigáciu webu. "
        "Ak je v texte viacjazyčný obsah, preferuj slovenskú sekciu OBSAH pred CONTENTS alebo INHALT. "
        "Ak je uvedený slovenský aj anglický názov oddelený lomkou, do title daj slovenský názov. "
        "Anglický preklad môžeš ignorovať. Autorov zapisuj ako 'Priezvisko, M.'; viac autorov rozdeľ do poľa. "
        "Pri stránkach použi tlačené strany článku z obsahu, napríklad '51' alebo '51-60'. "
        "Ak obsah uvádza iba začiatočnú stranu, zapíš iba túto stranu; rozsah sa dopočíta z ďalšieho článku. "
        "Extras obsahuje iba bibliografické skratky ako 'obr.', 'tab.', 'lit.', 'mapa', 'pl. j.', ak sú v obsahu. "
        "Abstract je krátka vecná anotácia po slovensky, 1 veta, iba z názvu a obsahu, bez vymýšľania. "
        "Caves obsahuje presné názvy jaskýň iba vtedy, keď sú explicitne v názve článku. "
        "has_map_plan nastav true iba pri explicitnej mape, pláne, pôdoryse, mapovej prílohe alebo rukopisných mapách. "
        "Vráť iba JSON podľa schémy.\n\n"
        f"Časopis: {item.get('journal_title')}\n"
        f"Ročník/číslo/rok: {item.get('volume')} / {item.get('issue')} / {item.get('year_label') or item.get('year')}\n"
        f"PDF: {item.get('pdf_url')}\n\n"
        f"TEXT:\n{context[:30000]}"
    )


def parse_articles_with_codex(item: dict[str, Any], context: str, model: str, timeout: int) -> list[dict[str, Any]]:
    data = run_codex_json(build_toc_prompt(item, context), ARTICLE_SCHEMA, model, timeout)
    articles = data.get("articles") or []
    return articles if isinstance(articles, list) else []


def minimum_article_count_for_issue(item: dict[str, Any]) -> int:
    if str(item.get("journal_id") or "") == "slovensky_kras":
        return 4
    return 1


def validate_parsed_articles(item: dict[str, Any], parsed_articles: list[dict[str, Any]]) -> None:
    minimum = minimum_article_count_for_issue(item)
    if len(parsed_articles) < minimum:
        raise RuntimeError(
            f"AI returned only {len(parsed_articles)} articles; expected at least {minimum} for this issue"
        )


def remove_existing_issue_articles(articles: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return [article for article in articles if article.get("source_issue_key") != key]


def copy_to_frontend(articles: list[dict[str, Any]], frontend_path: Path) -> None:
    write_json(frontend_path, articles)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--frontend", type=Path, default=DEFAULT_FRONTEND_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--journal", action="append", default=None, help="Journal id to process; default Aragonit and Slovenský kras.")
    parser.add_argument("--issue-key", action="append", default=None, help="Manifest issue key or source issue key to process.")
    parser.add_argument("--issue-key-file", type=Path, default=None, help="JSON/text file with issue keys to process.")
    parser.add_argument("--limit-issues", type=int, default=None)
    parser.add_argument("--toc-pages", type=int, default=10)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--force", action="store_true", help="Reimport selected issue keys and replace existing records for them.")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--force-page-map", action="store_true")
    parser.add_argument("--max-seconds", type=int, default=None, help="Stop cleanly after this many seconds, after finishing the current issue.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = read_json(args.manifest)
    articles = read_json(args.articles)
    existing_keys = existing_source_issue_keys(articles)
    journals = set(args.journal or DEFAULT_JOURNALS)
    include_keys = set(args.issue_key or [])
    if args.issue_key_file:
        include_keys.update(read_issue_key_file(args.issue_key_file))
    include_keys = include_keys or None
    items = select_manifest_items(
        manifest.get("items") or [],
        existing_keys=existing_keys,
        journals=journals,
        include_issue_keys=include_keys,
        force=args.force,
    )
    if args.limit_issues is not None:
        items = items[: args.limit_issues]

    started_at = utc_now()
    state: dict[str, Any] = {
        "status": "running",
        "started_at": started_at,
        "journals": sorted(journals),
        "total": len(items),
        "completed": 0,
        "failed": 0,
        "added_articles": 0,
        "dry_run": bool(args.dry_run),
        "current": None,
        "failures": [],
    }
    write_state(args.state, state)
    append_event(args.events, {"event": "run_start", "total": len(items), "journals": sorted(journals)})

    print(json.dumps({"selected_issues": len(items), "journals": sorted(journals)}, ensure_ascii=False))
    if args.dry_run:
        for item in items:
            print(f"{source_issue_key(item)} {item.get('year')} {item.get('pdf_url')}")
        state["status"] = "dry_run_complete"
        write_state(args.state, state)
        append_event(args.events, {"event": "dry_run_complete", "total": len(items)})
        return 0

    max_id = max((int(article.get("id") or 0) for article in articles), default=0)

    run_started_monotonic = time.monotonic()
    for index, item in enumerate(items, start=1):
        if time_budget_exhausted(
            start_monotonic=run_started_monotonic,
            now_monotonic=time.monotonic(),
            max_seconds=args.max_seconds,
            completed=int(state["completed"]),
        ):
            state["status"] = "partial_time_budget"
            state["current"] = None
            write_state(args.state, state)
            append_event(args.events, {"event": "run_partial_time_budget", "completed": state["completed"]})
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0

        key = source_issue_key(item)
        state["current"] = {"index": index, "key": key, "pdf_url": item.get("pdf_url")}
        write_state(args.state, state)
        append_event(args.events, {"event": "issue_start", "index": index, "key": key})
        print(f"[{index}/{len(items)}] {key}")

        try:
            pdf_path = download_issue_pdf(item, force=args.force_download)
            page_map = infer_printed_to_physical_page_map(
                pdf_path,
                fulltext.TEXT_CACHE_DIR / f"{fulltext.safe_name(str(item.get('pdf_url')))}.journal-pages.json",
                force=args.force_page_map,
            )
            context = build_issue_context(item, pdf_path, args.toc_pages)
            if not context:
                raise RuntimeError("No TOC context extracted")
            parsed = parse_articles_with_codex(item, context, args.model, args.timeout)
            if not parsed:
                raise RuntimeError("AI returned no articles")
            validate_parsed_articles(item, parsed)
            if args.force:
                articles = remove_existing_issue_articles(articles, key)
                max_id = max((int(article.get("id") or 0) for article in articles), default=0)
            records = build_article_records(
                item,
                parsed,
                start_id=max_id + 1,
                printed_to_physical=page_map,
                created_at=utc_now(),
                model=args.model,
            )
            if not records:
                raise RuntimeError("No usable article records built")
            articles.extend(records)
            max_id = max(int(article["id"]) for article in articles)
            write_json(args.articles, articles)
            copy_to_frontend(articles, args.frontend)
            state["completed"] += 1
            state["added_articles"] += len(records)
            append_event(args.events, {"event": "issue_finish", "key": key, "articles": len(records)})
            print(f"  added {len(records)} articles")
        except CodexAuthError:
            state["status"] = "blocked_auth"
            write_state(args.state, state)
            append_event(args.events, {"event": "run_blocked_auth", "key": key})
            raise
        except Exception as exc:
            state["failed"] += 1
            failure = {"key": key, "error": str(exc)[:600]}
            state["failures"].append(failure)
            append_event(args.events, {"event": "issue_failed", **failure})
            print(f"  failed: {exc}", file=sys.stderr)
        finally:
            write_state(args.state, state)
            time.sleep(0.2)

    state["status"] = "complete"
    state["current"] = None
    write_state(args.state, state)
    append_event(
        args.events,
        {
            "event": "run_finish",
            "completed": state["completed"],
            "failed": state["failed"],
            "added_articles": state["added_articles"],
        },
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0 if state["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
