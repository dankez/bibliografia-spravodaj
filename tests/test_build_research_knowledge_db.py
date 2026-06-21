import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_research_knowledge_db as research_db


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]):
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def sample_research_args(tmp_path: Path) -> argparse.Namespace:
    articles_path = tmp_path / "articles.json"
    fulltext_path = tmp_path / "fulltext.jsonl"
    ai_knowledge_path = tmp_path / "ai.jsonl"
    write_json(
        articles_path,
        [
            {
                "id": 1,
                "authors": ["Redakcia"],
                "title": "Výskum jaskyne Domica",
                "pages": "1-2",
                "year": 1970,
                "volume": "I.",
                "issue": "1",
                "abstract": "Správa o výskume jaskyne Domica.",
                "pdf_url": "https://sss.sk/spravodaj.pdf",
                "caves": ["Domica"],
                "tags": ["výskum"],
                "groups": [],
                "wikidata": [],
            },
            {
                "id": 2,
                "journal_id": "aragonit",
                "journal_title": "Aragonit",
                "journal_short_title": "Aragonit",
                "authors": ["Bella, P."],
                "title": "Ochrana jaskyne Domica",
                "pages": "51-60",
                "year": 2024,
                "volume": "29",
                "issue": "2",
                "abstract": "Článok o ochrane jaskyne Domica.",
                "pdf_url": "https://ssj.sk/aragonit.pdf",
                "pdf_page_start": 5,
                "pdf_page_end": 14,
                "pdf_page_offset": 0,
                "caves": ["Domica"],
                "tags": ["ochrana"],
                "groups": [],
                "wikidata": [],
            },
        ],
    )
    write_jsonl(
        fulltext_path,
        [
            {
                "id": 1,
                "text": "Výskum jaskyne Domica priniesol nové poznatky o hydrológii.",
                "status": "ok",
                "page_start": 1,
                "page_end": 2,
                "pdf_page_start": 3,
                "pdf_page_end": 4,
                "extracted_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": 2,
                "text": "Ochrana jaskyne Domica je dôležitá pre výskum aj návštevnosť.",
                "status": "ok",
                "page_start": 51,
                "page_end": 60,
                "pdf_page_start": 5,
                "pdf_page_end": 14,
                "pdf_page_offset": 0,
                "extracted_at": "2026-01-01T00:00:00+00:00",
            },
        ],
    )
    write_jsonl(ai_knowledge_path, [])
    return argparse.Namespace(
        articles=str(articles_path),
        fulltext=str(fulltext_path),
        ai_knowledge=str(ai_knowledge_path),
        db=str(tmp_path / "research.sqlite"),
        chunks_jsonl=str(tmp_path / "chunks.jsonl"),
        timelines=str(tmp_path / "timelines.json"),
        manifest=str(tmp_path / "manifest.json"),
        media_dir=str(tmp_path / "media"),
        chunk_chars=900,
        chunk_overlap=0,
        limit=None,
        force=True,
        only_with_fulltext=False,
        no_title_trim=True,
        render_pages=False,
        render_all_pages=False,
        extract_images=False,
        render_dpi=140,
        max_media_pages_per_article=6,
        timeline_min_articles=2,
        progress_every=0,
    )


def test_build_database_supports_multi_journal_fulltext_and_fts(tmp_path):
    args = sample_research_args(tmp_path)

    stats = research_db.build_database(args)

    assert stats["articles_total"] == 2
    assert stats["articles_with_fulltext"] == 2
    assert stats["journals"] == ["aragonit", "spravodaj_sss"]
    assert stats["chunks"] == 2

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        spravodaj = conn.execute("SELECT * FROM articles WHERE id = 1").fetchone()
        aragonit = conn.execute("SELECT * FROM articles WHERE id = 2").fetchone()
        assert spravodaj["journal_short_title"] == "Spravodaj SSS"
        assert spravodaj["pdf_page_start"] == 3
        assert "Spravodaj SSS" in spravodaj["citation_iso690"]
        assert "https://sss.sk/spravodaj.pdf#page=3" in spravodaj["citation_iso690"]

        assert aragonit["journal_short_title"] == "Aragonit"
        assert aragonit["pdf_page_start"] == 5
        assert "Aragonit" in aragonit["citation_iso690"]
        assert "https://ssj.sk/aragonit.pdf#page=5" in aragonit["citation_iso690"]

        assert conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0] == 2
    finally:
        conn.close()

    results = research_db.query_database(Path(args.db), "Domica", 10)
    assert {result["article_id"] for result in results} == {1, 2}
    assert {result["journal"] for result in results} == {"Spravodaj SSS", "Aragonit"}

    chunks = [json.loads(line) for line in Path(args.chunks_jsonl).read_text(encoding="utf-8").splitlines()]
    assert {chunk["journal"] for chunk in chunks} == {"Spravodaj SSS", "Aragonit"}
