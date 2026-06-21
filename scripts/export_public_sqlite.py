#!/usr/bin/env python3
"""Export public Spravodaj SSS bibliography data into a compact SQLite file."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "data" / "exports" / "spravodaj_sss.sqlite"
PDF_LINK_PAGE_OFFSET = 2
DEFAULT_JOURNAL_ID = "spravodaj_sss"
DEFAULT_JOURNAL_TITLE = "Spravodaj Slovenskej speleologickej spoločnosti"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        key = normalize_key(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def page_start(article: dict[str, Any]) -> int | None:
    value = article.get("pdf_page_start")
    if value in (None, ""):
        match = re.match(r"\s*(\d+)", str(article.get("pages") or ""))
        value = match.group(1) if match else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def pdf_page(article: dict[str, Any]) -> int | None:
    start = page_start(article)
    try:
        offset = int(article.get("pdf_page_offset", PDF_LINK_PAGE_OFFSET))
    except (TypeError, ValueError):
        offset = PDF_LINK_PAGE_OFFSET
    return start + offset if start is not None else None


def pdf_link(article: dict[str, Any]) -> str:
    url = str(article.get("pdf_url") or "").strip()
    page = pdf_page(article)
    if url and page:
        return f"{url}#page={page}"
    return url


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS export_metadata;
        DROP TABLE IF EXISTS map_plans;
        DROP TABLE IF EXISTS article_groups;
        DROP TABLE IF EXISTS groups;
        DROP TABLE IF EXISTS article_tags;
        DROP TABLE IF EXISTS tags;
        DROP TABLE IF EXISTS article_caves;
        DROP TABLE IF EXISTS caves;
        DROP TABLE IF EXISTS article_authors;
        DROP TABLE IF EXISTS authors;
        DROP TABLE IF EXISTS journals;
        DROP TABLE IF EXISTS articles;

        CREATE TABLE journals (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            short_title TEXT NOT NULL,
            pdf_page_offset INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            journal_id TEXT NOT NULL REFERENCES journals(id),
            journal_title TEXT NOT NULL,
            title TEXT NOT NULL,
            year INTEGER,
            volume TEXT,
            issue TEXT,
            pages TEXT,
            abstract TEXT,
            pdf_url TEXT,
            pdf_page INTEGER,
            pdf_link TEXT,
            has_map_plan INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE article_authors (
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            PRIMARY KEY (article_id, author_id)
        );

        CREATE TABLE caves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE article_caves (
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            cave_id INTEGER NOT NULL REFERENCES caves(id) ON DELETE CASCADE,
            PRIMARY KEY (article_id, cave_id)
        );

        CREATE TABLE tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE article_tags (
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (article_id, tag_id)
        );

        CREATE TABLE groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE article_groups (
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            PRIMARY KEY (article_id, group_id)
        );

        CREATE TABLE map_plans (
            article_id INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
            pages_json TEXT NOT NULL,
            score REAL,
            evidence_json TEXT NOT NULL
        );

        CREATE TABLE export_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX idx_articles_year_issue ON articles(year, issue);
        CREATE INDEX idx_articles_title ON articles(title);
        CREATE INDEX idx_article_authors_author ON article_authors(author_id);
        CREATE INDEX idx_article_caves_cave ON article_caves(cave_id);
        """
    )


def ensure_lookup(conn: sqlite3.Connection, table: str, name: str) -> int:
    key = normalize_key(name)
    conn.execute(
        f"INSERT OR IGNORE INTO {table}(name, normalized_name) VALUES (?, ?)",
        (name, key),
    )
    row = conn.execute(f"SELECT id FROM {table} WHERE normalized_name = ?", (key,)).fetchone()
    return int(row[0])


def journal_id(article: dict[str, Any]) -> str:
    return str(article.get("journal_id") or DEFAULT_JOURNAL_ID)


def journal_title(article: dict[str, Any]) -> str:
    return str(article.get("journal_title") or DEFAULT_JOURNAL_TITLE)


def journal_short_title(article: dict[str, Any]) -> str:
    return str(article.get("journal_short_title") or journal_title(article))


def article_pdf_page_offset(article: dict[str, Any]) -> int:
    try:
        return int(article.get("pdf_page_offset", PDF_LINK_PAGE_OFFSET))
    except (TypeError, ValueError):
        return PDF_LINK_PAGE_OFFSET


def ensure_journal(conn: sqlite3.Connection, article: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO journals(id, title, short_title, pdf_page_offset)
        VALUES (?, ?, ?, ?)
        """,
        (
            journal_id(article),
            journal_title(article),
            journal_short_title(article),
            article_pdf_page_offset(article),
        ),
    )


def insert_many_to_many(
    conn: sqlite3.Connection,
    article_id: int,
    values: list[str],
    lookup_table: str,
    join_table: str,
    join_id_column: str,
) -> int:
    count = 0
    for value in unique_strings(values):
        lookup_id = ensure_lookup(conn, lookup_table, value)
        conn.execute(
            f"INSERT OR IGNORE INTO {join_table}(article_id, {join_id_column}) VALUES (?, ?)",
            (article_id, lookup_id),
        )
        count += 1
    return count


def insert_article(conn: sqlite3.Connection, article: dict[str, Any]) -> None:
    article_id = int(article["id"])
    ensure_journal(conn, article)
    has_map_plan = 1 if article.get("has_map_plan") or (article.get("map_plan_pages") or []) else 0
    conn.execute(
        """
        INSERT INTO articles(
            id, journal_id, journal_title, title, year, volume, issue, pages, abstract, pdf_url, pdf_page,
            pdf_link, has_map_plan, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_id,
            journal_id(article),
            journal_title(article),
            str(article.get("title") or ""),
            article.get("year"),
            str(article.get("volume") or ""),
            str(article.get("issue") or ""),
            str(article.get("pages") or ""),
            str(article.get("abstract") or ""),
            str(article.get("pdf_url") or ""),
            pdf_page(article),
            pdf_link(article),
            has_map_plan,
            json.dumps(article, ensure_ascii=False, sort_keys=True),
        ),
    )

    for position, author in enumerate(unique_strings(article.get("authors") or ["Anonymus"]), start=1):
        author_id = ensure_lookup(conn, "authors", author)
        conn.execute(
            "INSERT OR IGNORE INTO article_authors(article_id, author_id, position) VALUES (?, ?, ?)",
            (article_id, author_id, position),
        )

    insert_many_to_many(conn, article_id, article.get("caves") or [], "caves", "article_caves", "cave_id")
    insert_many_to_many(conn, article_id, article.get("tags") or [], "tags", "article_tags", "tag_id")
    insert_many_to_many(conn, article_id, article.get("groups") or [], "groups", "article_groups", "group_id")

    map_pages = article.get("map_plan_pages") or []
    if has_map_plan:
        detected_map = (article.get("detected_features") or {}).get("map_plan") or {}
        conn.execute(
            """
            INSERT INTO map_plans(article_id, pages_json, score, evidence_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                article_id,
                json.dumps(map_pages, ensure_ascii=False),
                article.get("map_plan_score") or detected_map.get("score"),
                json.dumps(detected_map.get("evidence") or [], ensure_ascii=False),
            ),
        )


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def export_database(articles: list[dict[str, Any]], output_path: Path) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    conn = sqlite3.connect(output_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        create_schema(conn)
        for article in sorted(articles, key=lambda item: int(item["id"])):
            insert_article(conn, article)
        summary = {
            "articles": count_rows(conn, "articles"),
            "journals": count_rows(conn, "journals"),
            "authors": count_rows(conn, "authors"),
            "caves": count_rows(conn, "caves"),
            "tags": count_rows(conn, "tags"),
            "groups": count_rows(conn, "groups"),
            "map_plan_articles": count_rows(conn, "map_plans"),
        }
        metadata = {
            "created_at": utc_now(),
            "source": str(DEFAULT_ARTICLES_PATH.relative_to(BASE_DIR)),
            **{key: str(value) for key, value in summary.items()},
        }
        for key, value in metadata.items():
            conn.execute("INSERT INTO export_metadata(key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        return summary
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    articles = json.loads(args.articles.read_text(encoding="utf-8"))
    summary = export_database(articles, args.output)
    print(json.dumps({"output": str(args.output), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
