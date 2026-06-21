import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_research_knowledge_db as research_db
import generate_research_brief as research_brief


def build_sample_db(tmp_path: Path) -> Path:
    articles_path = tmp_path / "articles.json"
    fulltext_path = tmp_path / "fulltext.jsonl"
    ai_path = tmp_path / "ai.jsonl"
    db_path = tmp_path / "research.sqlite"
    articles_path.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "authors": ["Redakcia"],
                    "title": "Domica v starších výskumoch",
                    "pages": "1",
                    "year": 1970,
                    "volume": "I.",
                    "issue": "1",
                    "abstract": "Starší výskum jaskyne Domica.",
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
                    "title": "Monitoring v jaskyni Domica",
                    "pages": "51-52",
                    "year": 2024,
                    "volume": "29",
                    "issue": "2",
                    "abstract": "Monitoring jaskyne Domica.",
                    "pdf_url": "https://ssj.sk/aragonit.pdf",
                    "pdf_page_start": 5,
                    "pdf_page_end": 6,
                    "pdf_page_offset": 0,
                    "caves": ["Domica"],
                    "tags": ["monitoring"],
                    "groups": [],
                    "wikidata": [],
                },
            ],
        ),
        encoding="utf-8",
    )
    fulltext_path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {
                    "id": 1,
                    "text": "Domica bola predmetom staršieho výskumu a dokumentácie.",
                    "status": "ok",
                    "page_start": 1,
                    "page_end": 1,
                    "pdf_page_start": 3,
                    "pdf_page_end": 3,
                },
                {
                    "id": 2,
                    "text": "Monitoring v jaskyni Domica sleduje ochranu a návštevnosť.",
                    "status": "ok",
                    "page_start": 51,
                    "page_end": 52,
                    "pdf_page_start": 5,
                    "pdf_page_end": 6,
                },
            ]
        ),
        encoding="utf-8",
    )
    ai_path.write_text("", encoding="utf-8")
    research_db.build_database(
        argparse.Namespace(
            articles=str(articles_path),
            fulltext=str(fulltext_path),
            ai_knowledge=str(ai_path),
            db=str(db_path),
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
    )
    return db_path


def test_generate_research_brief_finds_articles_and_renders_markdown(tmp_path):
    db_path = build_sample_db(tmp_path)

    brief = research_brief.build_brief(
        argparse.Namespace(
            query="jaskyňa Domica",
            db=str(db_path),
            top_articles=0,
            chunks_per_article=2,
            max_total_chars=5000,
            text_mode="chunks",
            journal=None,
        )
    )

    assert brief["matching_articles"] == 2
    assert brief["included_articles"] == 2
    assert [article["journal"] for article in brief["articles"]] == ["Spravodaj SSS", "Aragonit"]
    assert all(article["chunks"] for article in brief["articles"])

    markdown = research_brief.render_markdown(brief)
    assert "# Rešeršný balík: jaskyňa Domica" in markdown
    assert "Domica v starších výskumoch" in markdown
    assert "Monitoring v jaskyni Domica" in markdown
    assert "https://ssj.sk/aragonit.pdf#page=5" in markdown


def test_generate_research_brief_full_mode_reconstructs_text_from_chunks(tmp_path):
    db_path = build_sample_db(tmp_path)

    brief = research_brief.build_brief(
        argparse.Namespace(
            query="Monitoring Domica",
            db=str(db_path),
            top_articles=1,
            chunks_per_article=1,
            max_total_chars=5000,
            text_mode="full",
            journal=None,
        )
    )

    assert brief["included_articles"] == 1
    assert "Monitoring v jaskyni Domica sleduje ochranu" in brief["articles"][0]["full_text"]
