#!/usr/bin/env python3
"""
Build an offline research knowledge database for Spravodaj SSS articles.

This is the non-AI layer for later article generation. It consumes already
cached PDF text and metadata, then creates a SQLite database with:

- article metadata and full-text statistics
- chunked full text for retrieval-augmented AI writing, stored once in article_chunks
- FTS5 search over chunks, titles, authors, caves, groups, tags and locations
- entity links for caves, SSS groups, people, locations, tags and keywords
- citation strings and JSON-LD ScholarlyArticle payloads
- media/page references, with optional local PDF page/image extraction

The intent is to pay the pdftotext/image-processing cost once locally and let
future AI scripts retrieve small, source-linked context slices from SQLite.
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FULLTEXT_PATH = BASE_DIR / "data" / "article_fulltext.jsonl"
AI_KNOWLEDGE_PATH = BASE_DIR / "data" / "article_ai_knowledge.jsonl"
PDF_LINK_PAGE_OFFSET = 2
DB_PATH = BASE_DIR / "data" / "research_knowledge.sqlite"
CHUNKS_JSONL_PATH = BASE_DIR / "data" / "research_chunks.jsonl"
TIMELINES_PATH = BASE_DIR / "data" / "research_timelines.json"
MANIFEST_PATH = BASE_DIR / "data" / "research_manifest.json"
MEDIA_DIR = BASE_DIR / "data" / "research_media"
DEFAULT_JOURNAL_ID = "spravodaj_sss"
DEFAULT_JOURNAL_TITLE = "Spravodaj Slovenskej speleologickej spoločnosti"
DEFAULT_JOURNAL_SHORT_TITLE = "Spravodaj SSS"
JOURNAL_DEFAULT_PDF_PAGE_OFFSETS = {
    "aragonit": 2,
    "slovensky_kras": 0,
    "spravodaj_sss": 2,
}


VISUAL_PATTERNS = [
    r"\bobr\.",
    r"\bobraz",
    r"\bfoto",
    r"\bfotograf",
    r"\bsnim",
    r"\bsnimk",
    r"\bmapa",
    r"\bmapk",
    r"\bplan",
    r"\bpl[aá]n",
    r"\bpl\.\s*j\.",
    r"\bprofil",
    r"\brez\b",
    r"\bnakres",
    r"\bn[aá]kres",
    r"\bsitu[aá]ci",
    r"\bpolygon",
    r"\bpolyg[oó]n",
    r"\btopograf",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        key = normalize_key(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_page_start(pages: str) -> str:
    match = re.match(r"\s*(\d+)", str(pages or ""))
    return match.group(1) if match else "1"


def parse_page_range(pages: str) -> tuple[int | None, int | None]:
    cleaned = str(pages or "").replace("–", "-").replace("—", "-").replace(" ", "")
    match = re.match(r"^(\d+)(?:-(\d+))?", cleaned)
    if not match:
        return None, None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    return start, max(start, end)


def int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def article_journal_id(article: dict) -> str:
    return str(article.get("journal_id") or DEFAULT_JOURNAL_ID)


def article_journal_title(article: dict) -> str:
    return str(article.get("journal_title") or DEFAULT_JOURNAL_TITLE)


def article_journal_short_title(article: dict) -> str:
    if article.get("journal_short_title"):
        return str(article["journal_short_title"])
    if article_journal_id(article) == DEFAULT_JOURNAL_ID:
        return DEFAULT_JOURNAL_SHORT_TITLE
    return article_journal_title(article)


def article_pdf_page_offset(article: dict) -> int:
    journal_id = article_journal_id(article)
    if journal_id in JOURNAL_DEFAULT_PDF_PAGE_OFFSETS and not int_or_none(article.get("pdf_page_start")):
        return JOURNAL_DEFAULT_PDF_PAGE_OFFSETS[journal_id]
    try:
        return int(article.get("pdf_page_offset"))
    except (TypeError, ValueError):
        pass
    return JOURNAL_DEFAULT_PDF_PAGE_OFFSETS.get(journal_id, PDF_LINK_PAGE_OFFSET)


def has_imported_physical_pages(article: dict) -> bool:
    return bool(article.get("journal_id")) and int_or_none(article.get("pdf_page_start")) is not None


def resolve_article_pdf_page_start(article: dict, fulltext: dict | None = None) -> int | None:
    """Return the final physical PDF page used in links and citations."""
    if article.get("_pdf_page_start_resolved"):
        return int_or_none(article.get("pdf_page_start"))
    if has_imported_physical_pages(article):
        return int_or_none(article.get("pdf_page_start"))

    parsed_start, _ = parse_page_range(article.get("pages", ""))
    printed = int_or_none(article.get("page_start")) or parsed_start
    if printed is not None:
        return printed + article_pdf_page_offset(article)

    return int_or_none((fulltext or {}).get("pdf_page_start"))


def resolve_article_pdf_page_end(article: dict, fulltext: dict | None = None) -> int | None:
    if has_imported_physical_pages(article):
        return int_or_none(article.get("pdf_page_end")) or int_or_none(article.get("pdf_page_start"))
    start = resolve_article_pdf_page_start(article, fulltext)
    parsed_start, parsed_end = parse_page_range(article.get("pages", ""))
    printed_start = int_or_none(article.get("page_start")) or parsed_start
    printed_end = int_or_none(article.get("page_end")) or parsed_end
    if start is None or printed_start is None or printed_end is None:
        return int_or_none((fulltext or {}).get("pdf_page_end")) or start
    return max(start, start + max(printed_end - printed_start, 0))


def pdf_link_page(article: dict) -> str:
    page_number = resolve_article_pdf_page_start(article)
    if page_number is None:
        return ""
    return str(page_number)


def pdf_anchor_page(page: Any) -> str:
    number = int_or_none(page)
    return str(number or "")


def pdf_url_for_article(article: dict) -> str:
    pdf_url = article.get("pdf_url") or ""
    page = pdf_link_page(article)
    if pdf_url and page:
        return f"{pdf_url}#page={page}"
    return pdf_url


def authors_label(authors: list[str]) -> str:
    clean = unique_strings(authors)
    return ", ".join(clean) if clean else "Anonymus"


def normalize_pages(pages: str) -> str:
    return str(pages or "").strip().replace("-", " - ")


def citation_iso690(article: dict) -> str:
    authors = authors_label(article.get("authors") or [])
    year = article.get("year") or "b. r."
    issue = article.get("issue") or ""
    volume = article.get("volume") or ""
    pages = normalize_pages(article.get("pages") or "")
    journal = article_journal_short_title(article)
    parts = [
        f"{authors}. {article.get('title', '').strip()}.",
        f"{journal}, {year}",
    ]
    if volume:
        parts.append(f"roc. {volume}")
    if issue:
        parts.append(f"c. {issue}")
    if pages:
        parts.append(f"s. {pages}")
    online = pdf_url_for_article(article)
    if online:
        parts.append(f"Online: {online}")
    return ", ".join(parts).replace(".,", ".")


def citation_apa(article: dict) -> str:
    authors = authors_label(article.get("authors") or [])
    year = article.get("year") or "n.d."
    pages = normalize_pages(article.get("pages") or "")
    issue = article.get("issue") or ""
    suffix = f", {pages}" if pages else ""
    return f"{authors}. ({year}). {article.get('title', '').strip()}. {article_journal_short_title(article)}, {issue}{suffix}."


def citation_mla(article: dict) -> str:
    authors = authors_label(article.get("authors") or [])
    title = article.get("title", "").strip()
    year = article.get("year") or ""
    issue = article.get("issue") or ""
    pages = normalize_pages(article.get("pages") or "")
    parts = [f'{authors}. "{title}."', article_journal_short_title(article)]
    if issue:
        parts.append(f"no. {issue}")
    if year:
        parts.append(str(year))
    if pages:
        parts.append(f"pp. {pages}")
    return ", ".join(parts) + "."


def jsonld_scholarly_article(article: dict, entities: dict[str, list[str]]) -> dict:
    keywords = unique_strings(
        as_list(article.get("tags"))
        + as_list(article.get("caves"))
        + as_list(article.get("groups"))
        + as_list((article.get("knowledge") or {}).get("keywords"))
    )
    payload = {
        "@context": "https://schema.org",
        "@type": "ScholarlyArticle",
        "identifier": f"{article_journal_id(article)}-{article.get('id')}",
        "name": article.get("title", ""),
        "headline": article.get("title", ""),
        "author": [{"@type": "Person", "name": author} for author in article.get("authors", [])],
        "datePublished": str(article.get("year") or ""),
        "isPartOf": {"@type": "Periodical", "name": article_journal_title(article)},
        "pagination": article.get("pages", ""),
        "url": pdf_url_for_article(article),
        "abstract": article.get("abstract", ""),
        "keywords": keywords,
        "about": [
            {"@type": "Thing", "name": name}
            for name in unique_strings(
                entities.get("cave", [])
                + entities.get("location", [])
                + entities.get("theme", [])
                + entities.get("keyword", [])
            )
        ],
    }
    return {key: value for key, value in payload.items() if value not in ("", [], None)}


def clean_fulltext(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x0c", "\n")
    text = re.sub(r"(?m)^\s*-+\s*\d{1,4}\s*-+\s*$", "", text)
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalized_char_stream(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(text):
        decomposed = unicodedata.normalize("NFKD", char)
        for item in decomposed:
            if unicodedata.combining(item):
                continue
            item = item.casefold()
            if item.isalnum():
                chars.append(item)
                positions.append(index)
    return "".join(chars), positions


def normalized_needle(text: str) -> str:
    return normalized_char_stream(text)[0]


def find_normalized_position(
    normalized_text: str,
    positions: list[int],
    needle: str,
    source_start: int = 0,
) -> int | None:
    normalized = normalized_needle(needle)
    if not normalized or len(normalized) < 4:
        return None
    start_index = bisect.bisect_left(positions, source_start)
    match_index = normalized_text.find(normalized, start_index)
    if match_index < 0:
        return None
    return positions[match_index]


def parse_page_start_int(article: dict) -> int:
    for value in (article.get("pdf_page_start"), article.get("page_start")):
        if isinstance(value, int):
            return value
    parsed = parse_page_start(article.get("pages", ""))
    try:
        return int(parsed)
    except ValueError:
        return 0


def build_next_titles_by_id(articles: list[dict], lookahead: int = 4) -> dict[int, list[str]]:
    grouped: dict[str, list[dict]] = {}
    for article in articles:
        url = str(article.get("pdf_url") or "")
        grouped.setdefault(url, []).append(article)

    result: dict[int, list[str]] = {}
    for issue_articles in grouped.values():
        ordered = sorted(issue_articles, key=lambda item: (parse_page_start_int(item), item.get("id", 0)))
        for index, article in enumerate(ordered):
            article_id = article.get("id")
            if not isinstance(article_id, int):
                continue
            titles = [
                str(item.get("title") or "").strip()
                for item in ordered[index + 1 : index + 1 + lookahead]
                if str(item.get("title") or "").strip()
            ]
            result[article_id] = titles
    return result


def trim_text_to_article_bounds(text: str, title: str, next_titles: list[str]) -> tuple[str, dict]:
    if not text.strip():
        return text, {"trimmed": False, "start": 0, "end": 0}
    normalized_text, positions = normalized_char_stream(text)
    if not normalized_text:
        return text, {"trimmed": False, "start": 0, "end": len(text)}

    start = 0
    title_position = find_normalized_position(normalized_text, positions, title)
    if title_position is not None and title_position < len(text) * 0.85:
        start = title_position

    end = len(text)
    search_start = start + max(80, len(title))
    for next_title in next_titles:
        next_position = find_normalized_position(normalized_text, positions, next_title, search_start)
        if next_position is not None and next_position > start + 120:
            end = min(end, next_position)

    trimmed = text[start:end].strip()
    if len(trimmed) < 80:
        return text, {"trimmed": False, "start": 0, "end": len(text)}
    changed = start > 0 or end < len(text)
    return trimmed, {
        "trimmed": changed,
        "start": start,
        "end": end,
        "removed_prefix_chars": start,
        "removed_suffix_chars": max(0, len(text) - end),
    }


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def chunk_text(text: str, max_chars: int, overlap_chars: int) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    max_chars = max(800, max_chars)
    overlap_chars = max(0, min(overlap_chars, max_chars // 3))
    chunks: list[dict] = []
    position = 0
    ordinal = 0
    text_length = len(text)

    while position < text_length:
        end = min(position + max_chars, text_length)
        if end < text_length:
            split_candidates = [
                text.rfind("\n\n", position, end),
                text.rfind(". ", position, end),
                text.rfind("\n", position, end),
                text.rfind("; ", position, end),
            ]
            split = max(split_candidates)
            if split > position + int(max_chars * 0.45):
                end = split + 1
        chunk = text[position:end].strip()
        if chunk:
            chunks.append(
                {
                    "ordinal": ordinal,
                    "start_char": position,
                    "end_char": end,
                    "text": chunk,
                    "word_count": word_count(chunk),
                }
            )
            ordinal += 1
        if end >= text_length:
            break
        next_position = end - overlap_chars
        if next_position <= position:
            next_position = end
        position = next_position
    return chunks


def page_for_chunk(record: dict, chunk: dict, text_length: int, physical: bool = True) -> int | None:
    if text_length <= 0:
        return None
    start_key = "pdf_page_start" if physical else "page_start"
    end_key = "pdf_page_end" if physical else "page_end"
    start = record.get(start_key)
    end = record.get(end_key)
    if not isinstance(start, int) or not isinstance(end, int):
        return start if isinstance(start, int) else None
    if end < start:
        end = start
    span = end - start + 1
    midpoint = (chunk["start_char"] + chunk["end_char"]) / 2
    page = start + int((midpoint / text_length) * span)
    return max(start, min(end, page))


def load_fulltext_by_id(path: Path) -> dict[int, dict]:
    records: dict[int, dict] = {}
    for record in iter_jsonl(path) or []:
        article_id = record.get("id")
        if isinstance(article_id, int):
            records[article_id] = record
    return records


def load_ai_knowledge_by_id(path: Path) -> dict[int, dict]:
    records: dict[int, dict] = {}
    for record in iter_jsonl(path) or []:
        article_id = record.get("article_id")
        if isinstance(article_id, int):
            records[article_id] = record
    return records


def detect_visual_terms(article: dict, text: str, knowledge: dict | None) -> list[str]:
    fields = [
        article.get("title", ""),
        article.get("abstract", ""),
        " ".join(as_list(article.get("extras"))),
        (knowledge or {}).get("map_or_plan_note", ""),
        text[:12000],
    ]
    haystack = "\n".join(str(field) for field in fields).casefold()
    found: list[str] = []
    for pattern in VISUAL_PATTERNS:
        if re.search(pattern, haystack):
            found.append(pattern)
    return found


def wikidata_map(article: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in as_list(article.get("wikidata")):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            url = str(item.get("url") or "").strip()
            if name and url:
                result[normalize_key(name)] = url
    return result


def merge_entities(article: dict, knowledge: dict | None) -> dict[str, list[str]]:
    knowledge = knowledge or {}
    article_knowledge = article.get("knowledge") or {}
    entities = {
        "cave": unique_strings(as_list(article.get("caves")) + as_list(knowledge.get("caves"))),
        "sss_group": unique_strings(as_list(article.get("groups")) + as_list(knowledge.get("sss_groups"))),
        "theme": unique_strings(
            as_list(article.get("tags"))
            + as_list(knowledge.get("themes"))
            + as_list(article_knowledge.get("keywords"))
        ),
        "keyword": unique_strings(as_list(knowledge.get("keywords")) + as_list(article_knowledge.get("keywords"))),
        "location": unique_strings(as_list(knowledge.get("locations")) + as_list(article_knowledge.get("locations"))),
        "person": unique_strings(as_list(article.get("authors")) + as_list(knowledge.get("people")) + as_list(article_knowledge.get("people"))),
    }
    return entities


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY,
            journal_id TEXT NOT NULL,
            journal_title TEXT NOT NULL,
            journal_short_title TEXT NOT NULL,
            title TEXT NOT NULL,
            authors_json TEXT NOT NULL,
            authors_text TEXT NOT NULL,
            year INTEGER,
            volume TEXT,
            issue TEXT,
            pages TEXT,
            page_start INTEGER,
            page_end INTEGER,
            pdf_page_start INTEGER,
            pdf_page_end INTEGER,
            pdf_page_offset INTEGER NOT NULL DEFAULT 0,
            pdf_url TEXT,
            pdf_cache TEXT,
            abstract TEXT,
            summary TEXT,
            lalkovic_note TEXT,
            text_chars INTEGER NOT NULL DEFAULT 0,
            word_count INTEGER NOT NULL DEFAULT 0,
            fulltext_status TEXT,
            text_trim_json TEXT NOT NULL,
            has_visual_material INTEGER NOT NULL DEFAULT 0,
            visual_terms_json TEXT NOT NULL,
            caves_json TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            groups_json TEXT NOT NULL,
            wikidata_json TEXT NOT NULL,
            keywords_json TEXT NOT NULL,
            locations_json TEXT NOT NULL,
            people_json TEXT NOT NULL,
            themes_json TEXT NOT NULL,
            citation_iso690 TEXT,
            citation_apa TEXT,
            citation_mla TEXT,
            jsonld_json TEXT NOT NULL,
            fulltext_extracted_at TEXT,
            knowledge_generated_at TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS article_chunks (
            chunk_id TEXT PRIMARY KEY,
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            start_char INTEGER NOT NULL,
            end_char INTEGER NOT NULL,
            text TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            printed_page INTEGER,
            pdf_page INTEGER,
            pdf_url TEXT,
            citation_label TEXT,
            created_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            content='article_chunks',
            content_rowid='rowid'
        );

        CREATE TABLE IF NOT EXISTS entities (
            entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            wikidata_url TEXT,
            source TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(entity_type, normalized_name)
        );

        CREATE TABLE IF NOT EXISTS article_entities (
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            entity_id INTEGER NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
            relation TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence REAL,
            PRIMARY KEY(article_id, entity_id, relation, source)
        );

        CREATE TABLE IF NOT EXISTS media_assets (
            asset_id TEXT PRIMARY KEY,
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            pdf_url TEXT,
            pdf_cache TEXT,
            page_start INTEGER,
            page_end INTEGER,
            page_number INTEGER,
            asset_type TEXT NOT NULL,
            path TEXT,
            caption TEXT,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS issue_pdfs (
            pdf_url TEXT PRIMARY KEY,
            pdf_cache TEXT,
            article_count INTEGER NOT NULL,
            min_year INTEGER,
            max_year INTEGER,
            first_article_id INTEGER,
            last_article_id INTEGER,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS build_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_article_chunks_article_id ON article_chunks(article_id);
        CREATE INDEX IF NOT EXISTS idx_articles_year_issue ON articles(year, issue);
        CREATE INDEX IF NOT EXISTS idx_entities_type_name ON entities(entity_type, normalized_name);
        CREATE INDEX IF NOT EXISTS idx_article_entities_article_id ON article_entities(article_id);
        CREATE INDEX IF NOT EXISTS idx_article_entities_entity_id ON article_entities(entity_id);
        CREATE INDEX IF NOT EXISTS idx_media_assets_article_id ON media_assets(article_id);

        CREATE VIEW IF NOT EXISTS entity_article_timeline AS
        SELECT
            e.entity_type,
            e.name,
            e.wikidata_url,
            a.id AS article_id,
            a.journal_id,
            a.journal_title,
            a.journal_short_title,
            a.year,
            a.issue,
            a.pages,
            a.title,
            a.authors_text,
            a.abstract,
            a.summary,
            a.pdf_url,
            a.pdf_page_start,
            ae.relation,
            ae.source
        FROM entities e
        JOIN article_entities ae ON ae.entity_id = e.entity_id
        JOIN articles a ON a.id = ae.article_id;
        """
    )


def reset_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP VIEW IF EXISTS entity_article_timeline;
        DROP TABLE IF EXISTS chunks_fts;
        DROP TABLE IF EXISTS chunks_fts_data;
        DROP TABLE IF EXISTS chunks_fts_idx;
        DROP TABLE IF EXISTS chunks_fts_content;
        DROP TABLE IF EXISTS chunks_fts_docsize;
        DROP TABLE IF EXISTS chunks_fts_config;
        DROP TABLE IF EXISTS media_assets;
        DROP TABLE IF EXISTS article_entities;
        DROP TABLE IF EXISTS entities;
        DROP TABLE IF EXISTS article_chunks;
        DROP TABLE IF EXISTS issue_pdfs;
        DROP TABLE IF EXISTS build_metadata;
        DROP TABLE IF EXISTS articles;
        """
    )
    create_schema(conn)


def upsert_entity(
    conn: sqlite3.Connection,
    entity_type: str,
    name: str,
    source: str,
    wikidata_url: str | None = None,
) -> int:
    normalized = normalize_key(name)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO entities(entity_type, name, normalized_name, wikidata_url, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_type, normalized_name) DO UPDATE SET
            name = excluded.name,
            wikidata_url = COALESCE(excluded.wikidata_url, entities.wikidata_url),
            source = CASE
                WHEN entities.source = excluded.source THEN entities.source
                ELSE entities.source || ',' || excluded.source
            END
        """,
        (entity_type, name, normalized, wikidata_url, source, now),
    )
    row = conn.execute(
        "SELECT entity_id FROM entities WHERE entity_type = ? AND normalized_name = ?",
        (entity_type, normalized),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Entity insert failed for {entity_type}:{name}")
    return int(row[0])


def link_article_entity(
    conn: sqlite3.Connection,
    article_id: int,
    entity_id: int,
    relation: str,
    source: str,
    confidence: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO article_entities(article_id, entity_id, relation, source, confidence)
        VALUES (?, ?, ?, ?, ?)
        """,
        (article_id, entity_id, relation, source, confidence),
    )


def article_row(
    article: dict,
    fulltext: dict | None,
    knowledge: dict | None,
    clean_text: str,
    trim_info: dict,
    visual_terms: list[str],
    entities: dict[str, list[str]],
) -> dict:
    knowledge = knowledge or {}
    article_knowledge = article.get("knowledge") or {}
    summary = knowledge.get("summary") or article_knowledge.get("summary") or ""
    keywords = unique_strings(as_list(knowledge.get("keywords")) + as_list(article_knowledge.get("keywords")))
    locations = unique_strings(as_list(knowledge.get("locations")) + as_list(article_knowledge.get("locations")))
    people = unique_strings(as_list(knowledge.get("people")) + as_list(article_knowledge.get("people")))
    themes = unique_strings(as_list(knowledge.get("themes")) + as_list(article.get("tags")))
    article_for_citation = dict(article)
    article_for_citation["pdf_page_start"] = resolve_article_pdf_page_start(article, fulltext)
    article_for_citation["pdf_page_end"] = resolve_article_pdf_page_end(article, fulltext)
    article_for_citation["pdf_page_offset"] = 0
    article_for_citation["_pdf_page_start_resolved"] = True
    jsonld = jsonld_scholarly_article(article_for_citation, entities)
    has_visual = bool(
        visual_terms
        or knowledge.get("has_map_or_plan")
        or article.get("has_map_plan")
        or (article.get("detected_features", {}).get("map_plan") or {}).get("present")
        or "map" in " ".join(as_list(article.get("extras"))).casefold()
    )
    return {
        "id": article["id"],
        "journal_id": article_journal_id(article),
        "journal_title": article_journal_title(article),
        "journal_short_title": article_journal_short_title(article),
        "title": article.get("title", ""),
        "authors_json": json_dumps(article.get("authors") or []),
        "authors_text": authors_label(article.get("authors") or []),
        "year": article.get("year"),
        "volume": article.get("volume", ""),
        "issue": str(article.get("issue", "")),
        "pages": article.get("pages", ""),
        "page_start": (fulltext or {}).get("page_start"),
        "page_end": (fulltext or {}).get("page_end"),
        "pdf_page_start": article_for_citation.get("pdf_page_start"),
        "pdf_page_end": article_for_citation.get("pdf_page_end"),
        "pdf_page_offset": 0,
        "pdf_url": article.get("pdf_url", ""),
        "pdf_cache": (fulltext or {}).get("pdf_cache", ""),
        "abstract": knowledge.get("bibliographic_abstract") or article.get("abstract", ""),
        "summary": summary,
        "lalkovic_note": knowledge.get("lalkovic_note", ""),
        "text_chars": len(clean_text),
        "word_count": word_count(clean_text),
        "fulltext_status": (
            f"{(fulltext or {}).get('status', 'missing')}+title_trimmed"
            if trim_info.get("trimmed")
            else (fulltext or {}).get("status", "missing")
        ),
        "text_trim_json": json_dumps(trim_info),
        "has_visual_material": 1 if has_visual else 0,
        "visual_terms_json": json_dumps(visual_terms),
        "caves_json": json_dumps(unique_strings(as_list(article.get("caves")) + as_list(knowledge.get("caves")))),
        "tags_json": json_dumps(unique_strings(as_list(article.get("tags")) + as_list(knowledge.get("themes")))),
        "groups_json": json_dumps(unique_strings(as_list(article.get("groups")) + as_list(knowledge.get("sss_groups")))),
        "wikidata_json": json_dumps(article.get("wikidata") or []),
        "keywords_json": json_dumps(keywords),
        "locations_json": json_dumps(locations),
        "people_json": json_dumps(people),
        "themes_json": json_dumps(themes),
        "citation_iso690": citation_iso690(article_for_citation),
        "citation_apa": citation_apa(article_for_citation),
        "citation_mla": citation_mla(article_for_citation),
        "jsonld_json": json_dumps(jsonld),
        "fulltext_extracted_at": (fulltext or {}).get("extracted_at"),
        "knowledge_generated_at": knowledge.get("generated_at") or article_knowledge.get("generated_at"),
        "updated_at": utc_now(),
    }


def insert_article(conn: sqlite3.Connection, row: dict) -> None:
    keys = list(row.keys())
    placeholders = ", ".join("?" for _ in keys)
    update = ", ".join(f"{key}=excluded.{key}" for key in keys if key != "id")
    conn.execute(
        f"""
        INSERT INTO articles({", ".join(keys)})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET {update}
        """,
        [row[key] for key in keys],
    )


def chunk_id(article_id: int, ordinal: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"a{article_id:06d}-c{ordinal:03d}-{digest}"


def insert_chunk(
    conn: sqlite3.Connection,
    article: dict,
    row: dict,
    chunk: dict,
    text_length: int,
) -> str:
    article_id = int(article["id"])
    cid = chunk_id(article_id, int(chunk["ordinal"]), chunk["text"])
    pdf_page = page_for_chunk(row, chunk, text_length, physical=True)
    printed_page = page_for_chunk(row, chunk, text_length, physical=False)
    citation_label = f"{row['authors_text']}: {row['title']} ({row.get('year')}, s. {row.get('pages')})"
    conn.execute(
        """
        INSERT OR REPLACE INTO article_chunks(
            chunk_id, article_id, ordinal, start_char, end_char, text, word_count,
            printed_page, pdf_page, pdf_url, citation_label, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cid,
            article_id,
            chunk["ordinal"],
            chunk["start_char"],
            chunk["end_char"],
            chunk["text"],
            chunk["word_count"],
            printed_page,
            pdf_page,
            row.get("pdf_url", ""),
            citation_label,
            utc_now(),
        ),
    )
    chunk_rowid = conn.execute("SELECT rowid FROM article_chunks WHERE chunk_id = ?", (cid,)).fetchone()[0]
    conn.execute(
        """
        INSERT INTO chunks_fts(rowid, text)
        VALUES (?, ?)
        """,
        (
            chunk_rowid,
            chunk["text"],
        ),
    )
    return cid


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def media_asset_id(article_id: int, asset_type: str, page: int | None, path: str | None) -> str:
    raw = f"{article_id}|{asset_type}|{page or ''}|{path or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def insert_media_asset(
    conn: sqlite3.Connection,
    article_id: int,
    pdf_url: str,
    pdf_cache: str,
    page_start: int | None,
    page_end: int | None,
    page_number: int | None,
    asset_type: str,
    path: str | None,
    caption: str,
    source: str,
    status: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO media_assets(
            asset_id, article_id, pdf_url, pdf_cache, page_start, page_end, page_number,
            asset_type, path, caption, source, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            media_asset_id(article_id, asset_type, page_number, path),
            article_id,
            pdf_url,
            pdf_cache,
            page_start,
            page_end,
            page_number,
            asset_type,
            path,
            caption,
            source,
            status,
            utc_now(),
        ),
    )


def render_article_pages(
    article_id: int,
    pdf_path: Path,
    page_start: int,
    page_end: int,
    media_dir: Path,
    dpi: int,
    max_pages: int,
) -> list[Path]:
    if not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm is required for --render-pages but was not found on PATH")
    if not pdf_path.exists():
        raise RuntimeError(f"PDF cache file does not exist: {pdf_path}")
    page_end = min(page_end, page_start + max_pages - 1)
    output_dir = media_dir / f"article_{article_id:06d}" / "pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "page"
    before = set(output_dir.glob("*.png"))
    cmd = [
        "pdftoppm",
        "-png",
        "-r",
        str(dpi),
        "-f",
        str(page_start),
        "-l",
        str(page_end),
        str(pdf_path),
        str(prefix),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"pdftoppm failed for {pdf_path}")
    after = set(output_dir.glob("*.png"))
    return sorted(after - before or after)


def extract_embedded_images(
    article_id: int,
    pdf_path: Path,
    page_start: int,
    page_end: int,
    media_dir: Path,
    max_pages: int,
) -> list[Path]:
    if not shutil.which("pdfimages"):
        raise RuntimeError("pdfimages is required for --extract-images but was not found on PATH")
    if not pdf_path.exists():
        raise RuntimeError(f"PDF cache file does not exist: {pdf_path}")
    page_end = min(page_end, page_start + max_pages - 1)
    output_dir = media_dir / f"article_{article_id:06d}" / "embedded"
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "image"
    before = set(output_dir.glob("*"))
    cmd = [
        "pdfimages",
        "-png",
        "-f",
        str(page_start),
        "-l",
        str(page_end),
        str(pdf_path),
        str(prefix),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"pdfimages failed for {pdf_path}")
    after = {path for path in output_dir.glob("*") if path.is_file()}
    return sorted(after - before or after)


def insert_media_references(
    conn: sqlite3.Connection,
    article_id: int,
    row: dict,
    has_visual: bool,
    args: argparse.Namespace,
) -> tuple[int, int]:
    media_count = 0
    media_errors = 0
    page_start = row.get("pdf_page_start")
    page_end = row.get("pdf_page_end") or page_start
    pdf_url = row.get("pdf_url") or ""
    pdf_cache = row.get("pdf_cache") or ""
    if pdf_url:
        insert_media_asset(
            conn,
            article_id,
            pdf_url,
            pdf_cache,
            page_start,
            page_end,
            page_start,
            "pdf_page_range",
            None,
            "Source PDF page range for the article.",
            "metadata",
            "reference",
        )
        media_count += 1

    if not page_start or not page_end or not pdf_cache:
        return media_count, media_errors
    if not has_visual and not args.render_all_pages:
        return media_count, media_errors

    pdf_path = BASE_DIR / pdf_cache
    if args.render_pages:
        try:
            for path in render_article_pages(
                article_id,
                pdf_path,
                int(page_start),
                int(page_end),
                Path(args.media_dir),
                args.render_dpi,
                args.max_media_pages_per_article,
            ):
                insert_media_asset(
                    conn,
                    article_id,
                    pdf_url,
                    pdf_cache,
                    page_start,
                    page_end,
                    None,
                    "rendered_pdf_page",
                    relative_path(path),
                    "Rendered local page image for later editorial/AI use.",
                    "pdftoppm",
                    "ok",
                )
                media_count += 1
        except Exception as exc:
            media_errors += 1
            print(f"Media render failed for article {article_id}: {exc}", file=sys.stderr)

    if args.extract_images:
        try:
            for path in extract_embedded_images(
                article_id,
                pdf_path,
                int(page_start),
                int(page_end),
                Path(args.media_dir),
                args.max_media_pages_per_article,
            ):
                insert_media_asset(
                    conn,
                    article_id,
                    pdf_url,
                    pdf_cache,
                    page_start,
                    page_end,
                    None,
                    "embedded_pdf_image",
                    relative_path(path),
                    "Embedded PDF image extracted locally.",
                    "pdfimages",
                    "ok",
                )
                media_count += 1
        except Exception as exc:
            media_errors += 1
            print(f"Image extraction failed for article {article_id}: {exc}", file=sys.stderr)
    return media_count, media_errors


def write_chunks_jsonl(path: Path, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def build_issue_pdf_table(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT
            pdf_url,
            MAX(pdf_cache) AS pdf_cache,
            COUNT(*) AS article_count,
            MIN(year) AS min_year,
            MAX(year) AS max_year,
            MIN(id) AS first_article_id,
            MAX(id) AS last_article_id
        FROM articles
        WHERE pdf_url IS NOT NULL AND pdf_url != ''
        GROUP BY pdf_url
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO issue_pdfs(
                pdf_url, pdf_cache, article_count, min_year, max_year,
                first_article_id, last_article_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*row, utc_now()),
        )


def write_build_metadata(conn: sqlite3.Connection, manifest: dict) -> None:
    for key, value in manifest.items():
        conn.execute(
            "INSERT OR REPLACE INTO build_metadata(key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value),
        )


def build_timelines(conn: sqlite3.Connection, path: Path, min_articles: int) -> int:
    rows = conn.execute(
        """
        SELECT
            e.entity_type,
            e.name,
            e.wikidata_url,
            a.id,
            a.journal_short_title,
            a.year,
            a.issue,
            a.pages,
            a.title,
            a.authors_text,
            COALESCE(NULLIF(a.summary, ''), a.abstract) AS summary,
            a.pdf_url,
            a.pdf_page_start
        FROM entities e
        JOIN article_entities ae ON ae.entity_id = e.entity_id
        JOIN articles a ON a.id = ae.article_id
        WHERE e.entity_type IN ('cave', 'sss_group', 'location', 'person')
        GROUP BY e.entity_type, e.name, a.id
        ORDER BY e.entity_type, e.name, a.year, a.id
        """
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        (
            entity_type,
            name,
            wikidata_url,
            article_id,
            journal_short_title,
            year,
            issue,
            pages,
            title,
            authors,
            summary,
            pdf_url,
            pdf_page,
        ) = row
        pdf_link_page_value = pdf_anchor_page(pdf_page)
        key = f"{entity_type}:{normalize_key(name)}"
        entry = grouped.setdefault(
            key,
            {
                "entity_type": entity_type,
                "name": name,
                "wikidata_url": wikidata_url,
                "article_count": 0,
                "articles": [],
            },
        )
        entry["articles"].append(
            {
                "article_id": article_id,
                "journal": journal_short_title,
                "year": year,
                "issue": issue,
                "pages": pages,
                "title": title,
                "authors": authors,
                "summary": summary,
                "pdf_url": f"{pdf_url}#page={pdf_link_page_value}" if pdf_url and pdf_link_page_value else pdf_url,
            }
        )
    timelines = []
    for value in grouped.values():
        value["article_count"] = len(value["articles"])
        if value["article_count"] >= min_articles or value["entity_type"] in {"cave", "sss_group"}:
            timelines.append(value)
    timelines.sort(key=lambda item: (-item["article_count"], item["entity_type"], item["name"]))
    path.write_text(json.dumps(timelines, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(timelines)


def build_database(args: argparse.Namespace) -> dict:
    db_path = Path(args.db)
    if args.force and db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Path(args.media_dir).mkdir(parents=True, exist_ok=True)

    articles = read_json(Path(args.articles), [])
    if not isinstance(articles, list):
        raise RuntimeError(f"Expected a list in {args.articles}")
    if args.limit:
        articles = articles[: args.limit]
    next_titles_by_id = build_next_titles_by_id(articles)

    fulltext_by_id = load_fulltext_by_id(Path(args.fulltext))
    knowledge_by_id = load_ai_knowledge_by_id(Path(args.ai_knowledge))

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    reset_database(conn)

    all_chunk_exports: list[dict] = []
    stats = {
        "generated_at": utc_now(),
        "db": relative_path(db_path),
        "articles_input": relative_path(Path(args.articles)),
        "fulltext_input": relative_path(Path(args.fulltext)),
        "ai_knowledge_input": relative_path(Path(args.ai_knowledge)),
        "articles_total": len(articles),
        "journals": sorted({article_journal_id(article) for article in articles if isinstance(article.get("id"), int)}),
        "articles_with_fulltext": 0,
        "articles_with_ai_knowledge": 0,
        "chunks": 0,
        "entities": 0,
        "article_entity_links": 0,
        "media_assets": 0,
        "media_errors": 0,
        "visual_candidate_articles": 0,
        "title_trimmed_articles": 0,
        "text_chars": 0,
        "words": 0,
        "timelines": 0,
    }

    wikidata_cache: dict[int, dict[str, str]] = {}

    with conn:
        for index, article in enumerate(articles, start=1):
            article_id = article.get("id")
            if not isinstance(article_id, int):
                continue
            fulltext = fulltext_by_id.get(article_id)
            knowledge = knowledge_by_id.get(article_id)
            raw_text = (fulltext or {}).get("text") or ""
            if args.no_title_trim:
                scoped_text = raw_text
                trim_info = {"trimmed": False, "start": 0, "end": len(raw_text), "mode": "disabled"}
            else:
                scoped_text, trim_info = trim_text_to_article_bounds(
                    raw_text,
                    str(article.get("title") or ""),
                    next_titles_by_id.get(article_id, []),
                )
                trim_info["mode"] = "title_bounds"
            clean_text = clean_fulltext(scoped_text)
            if args.only_with_fulltext and not clean_text:
                continue
            if clean_text:
                stats["articles_with_fulltext"] += 1
            if knowledge:
                stats["articles_with_ai_knowledge"] += 1

            entities = merge_entities(article, knowledge)
            visual_terms = detect_visual_terms(article, clean_text, knowledge)
            row = article_row(article, fulltext, knowledge, clean_text, trim_info, visual_terms, entities)
            insert_article(conn, row)
            stats["text_chars"] += row["text_chars"]
            stats["words"] += row["word_count"]
            if row["has_visual_material"]:
                stats["visual_candidate_articles"] += 1
            if trim_info.get("trimmed"):
                stats["title_trimmed_articles"] += 1

            wikidata_cache[article_id] = wikidata_map(article)
            confidence = None
            if knowledge and isinstance(knowledge.get("confidence"), (int, float)):
                confidence = float(knowledge["confidence"])

            for author in as_list(article.get("authors")):
                if not str(author).strip():
                    continue
                entity_id = upsert_entity(conn, "person", str(author), "bibliography")
                link_article_entity(conn, article_id, entity_id, "author", "bibliography", None)

            for entity_type, names in entities.items():
                relation = "mentioned"
                if entity_type == "theme":
                    relation = "theme"
                elif entity_type == "keyword":
                    relation = "keyword"
                elif entity_type == "cave":
                    relation = "cave"
                elif entity_type == "sss_group":
                    relation = "group"
                elif entity_type == "person":
                    relation = "person"
                for name in names:
                    source = "ai_knowledge" if knowledge and name in as_list(knowledge.get("keywords")) + as_list(knowledge.get("caves")) + as_list(knowledge.get("locations")) + as_list(knowledge.get("people")) + as_list(knowledge.get("themes")) + as_list(knowledge.get("sss_groups")) else "metadata"
                    entity_id = upsert_entity(
                        conn,
                        entity_type,
                        name,
                        source,
                        wikidata_cache[article_id].get(normalize_key(name)),
                    )
                    link_article_entity(conn, article_id, entity_id, relation, source, confidence)

            chunks = chunk_text(clean_text, args.chunk_chars, args.chunk_overlap)
            for chunk in chunks:
                cid = insert_chunk(conn, article, row, chunk, max(1, len(clean_text)))
                export_record = {
                    "chunk_id": cid,
                    "article_id": article_id,
                    "ordinal": chunk["ordinal"],
                    "journal": row["journal_short_title"],
                    "journal_id": row["journal_id"],
                    "title": row["title"],
                    "authors": row["authors_text"],
                    "year": row["year"],
                    "issue": row["issue"],
                    "pages": row["pages"],
                    "pdf_url": f"{row['pdf_url']}#page={pdf_anchor_page(page_for_chunk(row, chunk, max(1, len(clean_text)), physical=True))}"
                    if row.get("pdf_url")
                    else "",
                    "citation": row["citation_iso690"],
                    "text": chunk["text"],
                }
                all_chunk_exports.append(export_record)
            stats["chunks"] += len(chunks)

            media_count, media_errors = insert_media_references(
                conn,
                article_id,
                row,
                bool(row["has_visual_material"]),
                args,
            )
            stats["media_assets"] += media_count
            stats["media_errors"] += media_errors

            if args.progress_every and index % args.progress_every == 0:
                print(f"Processed {index}/{len(articles)} articles, chunks={stats['chunks']}")

        build_issue_pdf_table(conn)
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('optimize')")
        stats["entities"] = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        stats["article_entity_links"] = conn.execute("SELECT COUNT(*) FROM article_entities").fetchone()[0]
        stats["media_assets"] = conn.execute("SELECT COUNT(*) FROM media_assets").fetchone()[0]
        stats["issue_pdfs"] = conn.execute("SELECT COUNT(*) FROM issue_pdfs").fetchone()[0]
        stats["sqlite_fts5"] = True

    write_chunks_jsonl(Path(args.chunks_jsonl), all_chunk_exports)
    stats["chunks_jsonl"] = relative_path(Path(args.chunks_jsonl))
    with conn:
        stats["timelines"] = build_timelines(conn, Path(args.timelines), args.timeline_min_articles)
        stats["timelines_json"] = relative_path(Path(args.timelines))
        write_build_metadata(conn, stats)
    Path(args.manifest).write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return stats


def search_prefix(token: str) -> str:
    suffixes = [
        "skeho",
        "skemu",
        "skych",
        "skymi",
        "ami",
        "ymi",
        "eho",
        "emu",
        "ej",
        "ou",
        "om",
        "ho",
        "mu",
        "ch",
        "mi",
        "ia",
        "ie",
        "e",
        "a",
        "u",
        "y",
        "i",
    ]
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def fts_query_from_user(query: str, operator: str = "AND") -> str:
    tokens = [token for token in normalize_key(query).split() if len(token) > 1]
    if not tokens:
        return query
    joiner = f" {operator} "
    return joiner.join(f"{search_prefix(token)}*" for token in tokens)


def query_database(db_path: Path, query: str, limit: int) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    def run_fts(fts_query: str):
        return conn.execute(
                """
                SELECT
                    c.chunk_id,
                    c.article_id,
                    a.year,
                    a.issue,
                    a.journal_short_title,
                    a.pages,
                    a.title,
                    a.authors_text,
                    c.ordinal,
                    c.pdf_page,
                    c.citation_label,
                    c.text,
                    snippet(chunks_fts, 0, '[', ']', '...', 24) AS snippet,
                    bm25(chunks_fts) AS score
                FROM chunks_fts f
                JOIN article_chunks c ON c.rowid = f.rowid
                JOIN articles a ON a.id = c.article_id
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()

    try:
        rows = run_fts(fts_query_from_user(query, "AND"))
        if not rows and len(normalize_key(query).split()) > 1:
            rows = run_fts(fts_query_from_user(query, "OR"))
    except sqlite3.OperationalError:
        like = f"%{query}%"
        rows = conn.execute(
            """
            SELECT
                c.chunk_id,
                c.article_id,
                a.year,
                a.issue,
                a.journal_short_title,
                a.pages,
                a.title,
                a.authors_text,
                c.ordinal,
                c.pdf_page,
                c.citation_label,
                c.text,
                substr(c.text, 1, 500) AS snippet,
                0.0 AS score
            FROM article_chunks c
            JOIN articles a ON a.id = c.article_id
            WHERE c.text LIKE ? OR a.title LIKE ? OR a.authors_text LIKE ?
            LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
    results: list[dict] = []
    for row in rows:
        pdf_url = ""
        article_row_data = conn.execute(
            "SELECT pdf_url FROM articles WHERE id = ?",
            (row["article_id"],),
        ).fetchone()
        if article_row_data and article_row_data["pdf_url"]:
            pdf_url = article_row_data["pdf_url"]
            if row["pdf_page"]:
                pdf_url = f"{pdf_url}#page={pdf_anchor_page(row['pdf_page'])}"
        results.append(
            {
                "chunk_id": row["chunk_id"],
                "article_id": row["article_id"],
                "journal": row["journal_short_title"],
                "year": row["year"],
                "issue": row["issue"],
                "pages": row["pages"],
                "title": row["title"],
                "authors": row["authors_text"],
                "chunk_ordinal": row["ordinal"],
                "pdf_page": row["pdf_page"],
                "pdf_url": pdf_url,
                "citation": row["citation_label"],
                "score": row["score"],
                "snippet": row["snippet"],
                "text": row["text"],
            }
        )
    conn.close()
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build/query the local Spravodaj SSS research knowledge database."
    )
    parser.add_argument("--articles", default=str(ARTICLES_PATH), help="Bibliographic articles JSON.")
    parser.add_argument("--fulltext", default=str(FULLTEXT_PATH), help="Article fulltext JSONL.")
    parser.add_argument("--ai-knowledge", default=str(AI_KNOWLEDGE_PATH), help="AI knowledge JSONL.")
    parser.add_argument("--db", default=str(DB_PATH), help="Output SQLite database.")
    parser.add_argument("--chunks-jsonl", default=str(CHUNKS_JSONL_PATH), help="Chunk export JSONL.")
    parser.add_argument("--timelines", default=str(TIMELINES_PATH), help="Entity timeline export JSON.")
    parser.add_argument("--manifest", default=str(MANIFEST_PATH), help="Build manifest JSON.")
    parser.add_argument("--media-dir", default=str(MEDIA_DIR), help="Directory for optional media files.")
    parser.add_argument("--chunk-chars", type=int, default=3200, help="Approximate max chunk size in chars.")
    parser.add_argument("--chunk-overlap", type=int, default=350, help="Character overlap between chunks.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N articles.")
    parser.add_argument("--force", action="store_true", help="Rebuild database from scratch.")
    parser.add_argument("--only-with-fulltext", action="store_true", help="Skip metadata-only articles.")
    parser.add_argument("--no-title-trim", action="store_true", help="Disable local title-boundary text trimming.")
    parser.add_argument("--render-pages", action="store_true", help="Render article PDF pages to PNG files.")
    parser.add_argument("--render-all-pages", action="store_true", help="Render all article pages, not only visual candidates.")
    parser.add_argument("--extract-images", action="store_true", help="Extract embedded PDF images locally.")
    parser.add_argument("--render-dpi", type=int, default=140, help="DPI for --render-pages.")
    parser.add_argument("--max-media-pages-per-article", type=int, default=6, help="Safety limit for page/image extraction.")
    parser.add_argument("--timeline-min-articles", type=int, default=2, help="Minimum articles for exported non-cave timelines.")
    parser.add_argument("--progress-every", type=int, default=250, help="Print progress every N articles; 0 disables.")
    parser.add_argument("--query", default=None, help="Query existing or newly built SQLite FTS database.")
    parser.add_argument("--query-only", action="store_true", help="Do not rebuild, only query --db.")
    parser.add_argument("--top", type=int, default=10, help="Number of query results.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)

    if args.query and args.query_only:
        if not db_path.exists():
            print(f"Database does not exist: {db_path}", file=sys.stderr)
            return 1
    else:
        stats = build_database(args)
        print(
            "Built research DB: "
            f"articles={stats['articles_total']}, "
            f"fulltext={stats['articles_with_fulltext']}, "
            f"chunks={stats['chunks']}, "
            f"entities={stats['entities']}, "
            f"media={stats['media_assets']}, "
            f"db={stats['db']}"
        )

    if args.query:
        results = query_database(db_path, args.query, args.top)
        print(json.dumps({"query": args.query, "results": results}, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
