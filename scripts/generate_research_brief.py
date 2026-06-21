#!/usr/bin/env python3
"""Generate an AI-ready research brief from the local fulltext knowledge DB."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Any

import build_research_knowledge_db as research


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "research_knowledge.sqlite"
DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "research_briefs"
JOURNAL_ORDER = {
    "spravodaj_sss": 0,
    "aragonit": 1,
    "slovensky_kras": 2,
}
GENERIC_QUERY_TOKENS = {
    "jaskyna",
    "jaskyne",
    "jaskyni",
    "jaskyniach",
    "jaskynny",
    "jaskynne",
    "o",
    "a",
    "v",
    "vo",
    "na",
    "pre",
    "clanok",
    "resers",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_text = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return ascii_text or "research"


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def query_terms(query: str) -> list[str]:
    tokens = [token for token in research.normalize_key(query).split() if len(token) > 1]
    terms = [token for token in tokens if token not in GENERIC_QUERY_TOKENS]
    if not terms and tokens:
        terms = tokens
    combined = research.normalize_key(query)
    if combined and combined not in terms:
        terms.insert(0, combined)
    return terms


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fts_article_scores(conn: sqlite3.Connection, query: str) -> dict[int, float]:
    scores: dict[int, float] = {}

    def run(operator: str) -> list[sqlite3.Row]:
        return conn.execute(
            """
            SELECT
                c.article_id,
                MIN(bm25(chunks_fts)) AS score
            FROM chunks_fts f
            JOIN article_chunks c ON c.rowid = f.rowid
            WHERE chunks_fts MATCH ?
            GROUP BY c.article_id
            ORDER BY score
            """,
            (research.fts_query_from_user(query, operator),),
        ).fetchall()

    try:
        rows = run("AND")
        if not rows:
            rows = run("OR")
    except sqlite3.OperationalError:
        rows = []

    for row in rows:
        scores[int(row["article_id"])] = float(row["score"] or 0.0)
    return scores


def metadata_article_scores(conn: sqlite3.Connection, query: str) -> dict[int, float]:
    terms = query_terms(query)
    if not terms:
        return {}

    scores: dict[int, float] = {}
    for term in terms:
        like = f"%{term}%"
        entity_rows = conn.execute(
            """
            SELECT ae.article_id
            FROM entities e
            JOIN article_entities ae ON ae.entity_id = e.entity_id
            WHERE e.normalized_name LIKE ?
            """,
            (like,),
        ).fetchall()
        for row in entity_rows:
            scores[int(row["article_id"])] = min(scores.get(int(row["article_id"]), 0.0), -20.0)

        text_like = f"%{term}%"
        article_rows = conn.execute(
            """
            SELECT id
            FROM articles
            WHERE lower(title) LIKE ?
               OR lower(abstract) LIKE ?
               OR lower(summary) LIKE ?
               OR lower(caves_json) LIKE ?
               OR lower(keywords_json) LIKE ?
               OR lower(tags_json) LIKE ?
               OR lower(groups_json) LIKE ?
               OR lower(locations_json) LIKE ?
               OR lower(people_json) LIKE ?
               OR lower(themes_json) LIKE ?
               OR lower(authors_text) LIKE ?
            """,
            (
                text_like,
                text_like,
                text_like,
                text_like,
                text_like,
                text_like,
                text_like,
                text_like,
                text_like,
                text_like,
                text_like,
            ),
        ).fetchall()
        for row in article_rows:
            scores[int(row["id"])] = min(scores.get(int(row["id"]), 0.0), -5.0)
    return scores


def article_sort_key(row: sqlite3.Row) -> tuple:
    return (
        row["year"] if row["year"] is not None else 9999,
        JOURNAL_ORDER.get(row["journal_id"], 99),
        str(row["issue"] or ""),
        row["page_start"] if row["page_start"] is not None else 999999,
        row["id"],
    )


def load_articles(conn: sqlite3.Connection, article_ids: list[int]) -> list[sqlite3.Row]:
    if not article_ids:
        return []
    placeholders = ",".join("?" for _ in article_ids)
    rows = conn.execute(f"SELECT * FROM articles WHERE id IN ({placeholders})", article_ids).fetchall()
    return sorted(rows, key=article_sort_key)


def pdf_link(row: sqlite3.Row, page: int | None = None) -> str:
    url = row["pdf_url"] or ""
    if not url:
        return ""
    target_page = page or row["pdf_page_start"]
    if target_page:
        return f"{url}#page={target_page}"
    return url


def matching_chunks(
    conn: sqlite3.Connection,
    article_id: int,
    query: str,
    limit: int,
) -> list[sqlite3.Row]:
    if limit <= 0:
        return []
    try:
        rows = conn.execute(
            """
            SELECT
                c.*
            FROM chunks_fts f
            JOIN article_chunks c ON c.rowid = f.rowid
            WHERE c.article_id = ?
              AND chunks_fts MATCH ?
            ORDER BY bm25(chunks_fts), c.ordinal
            LIMIT ?
            """,
            (article_id, research.fts_query_from_user(query, "OR"), limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if rows:
        return rows

    terms = query_terms(query)
    if not terms:
        return []
    like_clauses = " OR ".join("lower(text) LIKE ?" for _ in terms)
    return conn.execute(
        f"""
        SELECT *
        FROM article_chunks
        WHERE article_id = ?
          AND ({like_clauses})
        ORDER BY ordinal
        LIMIT ?
        """,
        [article_id, *[f"%{term}%" for term in terms], limit],
    ).fetchall()


def article_text_from_chunks(conn: sqlite3.Connection, article_id: int) -> str:
    rows = conn.execute(
        """
        SELECT start_char, end_char, text
        FROM article_chunks
        WHERE article_id = ?
        ORDER BY ordinal
        """,
        (article_id,),
    ).fetchall()
    if not rows:
        return ""

    parts: list[str] = []
    last_end = 0
    for row in rows:
        text = str(row["text"] or "")
        start = int(row["start_char"] or 0)
        end = int(row["end_char"] or start + len(text))
        if not text:
            continue
        if parts and start < last_end:
            overlap = min(len(text), last_end - start)
            text = text[overlap:]
        if text:
            if parts and start > last_end:
                parts.append("\n\n")
            parts.append(text)
        last_end = max(last_end, end)
    return "".join(parts).strip()


def trim_text(value: str, max_chars: int) -> tuple[str, bool]:
    text = re.sub(r"\n{3,}", "\n\n", str(value or "").strip())
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "\n\n[...skrátené pre znakový rozpočet...]", True


def article_to_payload(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    query: str,
    chunks_per_article: int,
    text_mode: str,
    remaining_chars: int,
) -> tuple[dict[str, Any], int]:
    chunks = matching_chunks(conn, int(row["id"]), query, chunks_per_article)
    chunk_payloads = []
    used_chars = 0
    for chunk in chunks:
        text, shortened = trim_text(chunk["text"], max(0, remaining_chars - used_chars))
        if not text:
            break
        chunk_payloads.append(
            {
                "chunk_id": chunk["chunk_id"],
                "ordinal": chunk["ordinal"],
                "printed_page": chunk["printed_page"],
                "pdf_page": chunk["pdf_page"],
                "pdf_url": pdf_link(row, chunk["pdf_page"]),
                "text": text,
                "shortened": shortened,
            }
        )
        used_chars += len(text)
        if shortened or used_chars >= remaining_chars:
            break

    full_text = ""
    full_text_shortened = False
    if text_mode == "full" and remaining_chars - used_chars > 0:
        full_text, full_text_shortened = trim_text(
            article_text_from_chunks(conn, int(row["id"])),
            remaining_chars - used_chars,
        )
        used_chars += len(full_text)

    payload = {
        "article_id": row["id"],
        "journal_id": row["journal_id"],
        "journal": row["journal_short_title"],
        "year": row["year"],
        "volume": row["volume"],
        "issue": row["issue"],
        "pages": row["pages"],
        "title": row["title"],
        "authors": row["authors_text"],
        "abstract": row["abstract"],
        "summary": row["summary"],
        "citation": row["citation_iso690"],
        "pdf_url": pdf_link(row),
        "word_count": row["word_count"],
        "text_chars": row["text_chars"],
        "caves": json_loads(row["caves_json"], []),
        "keywords": json_loads(row["keywords_json"], []),
        "chunks": chunk_payloads,
    }
    if text_mode == "full":
        payload["full_text"] = full_text
        payload["full_text_shortened"] = full_text_shortened
    return payload, used_chars


def build_brief(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"Research DB does not exist: {db_path}")

    conn = connect(db_path)
    try:
        scores = fts_article_scores(conn, args.query)
        for article_id, score in metadata_article_scores(conn, args.query).items():
            scores[article_id] = min(scores.get(article_id, score), score)

        article_ids = [article_id for article_id, _ in sorted(scores.items(), key=lambda item: item[1])]
        if args.journal:
            allowed = set(args.journal)
            article_ids = [
                article_id
                for article_id in article_ids
                if conn.execute("SELECT journal_id FROM articles WHERE id = ?", (article_id,)).fetchone()["journal_id"]
                in allowed
            ]
        if args.top_articles and args.top_articles > 0:
            article_ids = article_ids[: args.top_articles]

        rows = load_articles(conn, article_ids)
        remaining_chars = args.max_total_chars
        articles = []
        for row in rows:
            payload, used = article_to_payload(
                conn,
                row,
                args.query,
                args.chunks_per_article,
                args.text_mode,
                max(0, remaining_chars),
            )
            articles.append(payload)
            remaining_chars -= used

        return {
            "query": args.query,
            "generated_at": utc_now(),
            "db": str(db_path),
            "text_mode": args.text_mode,
            "max_total_chars": args.max_total_chars,
            "matching_articles": len(article_ids),
            "included_articles": len(articles),
            "articles": articles,
        }
    finally:
        conn.close()


def render_markdown(brief: dict[str, Any]) -> str:
    lines = [
        f"# Rešeršný balík: {brief['query']}",
        "",
        f"- Vygenerované: {brief['generated_at']}",
        f"- Nájdené články: {brief['matching_articles']}",
        f"- Zahrnuté články: {brief['included_articles']}",
        f"- Režim textu: {brief['text_mode']}",
        "",
        "## Inštrukcia pre AI",
        "",
        (
            "Použi iba nižšie uvedené textové zdroje. Obrázky ani mapy nie sú súčasťou balíka; "
            "ak treba uviesť mapy/plány, odkazuj sa len na bibliografické údaje a PDF odkazy."
        ),
        "",
        "## Zdroje",
        "",
    ]
    for index, article in enumerate(brief["articles"], start=1):
        lines.extend(
            [
                f"### {index}. {article['year']} - {article['title']}",
                "",
                f"- Časopis: {article['journal']}",
                f"- Autori: {article['authors']}",
                f"- Ročník/číslo/strany: {article['volume']} / {article['issue']} / s. {article['pages']}",
                f"- PDF: {article['pdf_url']}",
                f"- Citácia: {article['citation']}",
            ]
        )
        summary = article.get("summary") or article.get("abstract")
        if summary:
            lines.extend(["", f"Anotácia: {summary}"])
        if article.get("full_text"):
            lines.extend(["", "#### Plný text", "", article["full_text"]])
        elif article["chunks"]:
            lines.extend(["", "#### Vybrané úryvky", ""])
            for chunk in article["chunks"]:
                page = f", PDF strana {chunk['pdf_page']}" if chunk.get("pdf_page") else ""
                lines.extend([f"Úryvok {chunk['ordinal']}{page}:", "", chunk["text"], ""])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Topic, cave, locality or phrase, e.g. Domica.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Research SQLite DB.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Default directory for generated briefs.")
    parser.add_argument("--output-md", default=None, help="Markdown output path.")
    parser.add_argument("--output-json", default=None, help="JSON output path.")
    parser.add_argument("--top-articles", type=int, default=0, help="Limit articles; 0 means all matching articles.")
    parser.add_argument("--chunks-per-article", type=int, default=3, help="Maximum matching chunks per article.")
    parser.add_argument("--max-total-chars", type=int, default=240_000, help="Total text budget for AI context.")
    parser.add_argument("--text-mode", choices=["chunks", "full"], default="chunks", help="Include selected chunks or full article text within the character budget.")
    parser.add_argument("--journal", action="append", choices=["spravodaj_sss", "aragonit", "slovensky_kras"], help="Restrict to a journal; can be repeated.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    brief = build_brief(args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(args.query)
    md_path = Path(args.output_md) if args.output_md else output_dir / f"{slug}.md"
    json_path = Path(args.output_json) if args.output_json else output_dir / f"{slug}.json"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(brief), encoding="utf-8")
    print(
        "Generated research brief: "
        f"query={args.query!r}, matching={brief['matching_articles']}, "
        f"included={brief['included_articles']}, md={md_path}, json={json_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
