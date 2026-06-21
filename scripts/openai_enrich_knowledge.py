#!/usr/bin/env python3
"""
Enrich article full text with Codex auth or OpenAI Structured Outputs.

Input:  data/article_fulltext.jsonl from extract_pdf_fulltext.py
Output: data/article_ai_knowledge.jsonl with structured summaries, entities,
        cave/group/tag suggestions, and Lalkovic-style notes.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

from codex_ai_backend import CodexAuthError, run_codex_json


BASE_DIR = Path(__file__).resolve().parents[1]
FULLTEXT_PATH = BASE_DIR / "data" / "article_fulltext.jsonl"
KNOWLEDGE_PATH = BASE_DIR / "data" / "article_ai_knowledge.jsonl"
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FRONTEND_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


KNOWLEDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "article_id": {"type": "integer"},
        "bibliographic_abstract": {
            "type": "string",
            "description": "1-2 sentence Slovak abstract suitable for a bibliography.",
        },
        "lalkovic_note": {
            "type": "string",
            "description": "One concise Slovak note in the style of the historic Lalkovic bibliography.",
        },
        "summary": {
            "type": "string",
            "description": "A factual Slovak summary of the article content, max 120 words.",
        },
        "keywords": {"type": "array", "items": {"type": "string"}},
        "caves": {"type": "array", "items": {"type": "string"}},
        "locations": {"type": "array", "items": {"type": "string"}},
        "sss_groups": {"type": "array", "items": {"type": "string"}},
        "people": {"type": "array", "items": {"type": "string"}},
        "themes": {"type": "array", "items": {"type": "string"}},
        "has_map_or_plan": {"type": "boolean"},
        "map_or_plan_note": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "article_id",
        "bibliographic_abstract",
        "lalkovic_note",
        "summary",
        "keywords",
        "caves",
        "locations",
        "sss_groups",
        "people",
        "themes",
        "has_map_or_plan",
        "map_or_plan_note",
        "confidence",
    ],
}


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            yield json.loads(line)


def load_done_ids(path: Path) -> set[int]:
    done: set[int] = set()
    for record in iter_jsonl(path) or []:
        article_id = record.get("article_id")
        if isinstance(article_id, int):
            done.add(article_id)
    return done


def extract_response_text(payload: dict) -> str:
    if payload.get("output_text"):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks).strip()


def build_knowledge_prompt(record: dict) -> str:
    text = (record.get("text") or "").strip()
    if len(text) > 28000:
        text = text[:28000] + "\n\n[TEXT SKRATENY PRE KONTEXT]"

    return (
        "Si odborny bibliograf a speleologicky redaktor pre casopis Spravodaj SSS. "
        "Spracuj dodany text clanku do strukturovaneho JSONu. "
        "Nevymyslaj fakty, mena, jaskyne ani skupiny. Ak text neobsahuje udaj, nechaj pole prazdne. "
        "Styl bibliografickej poznamky ma byt vecny a blizky historickej Bibliografii Spravodaja SSS: "
        "kratke zhrnutie obsahu, nie reklamny popis. "
        "Vrat iba JSON podla pozadovanej schemy.\n\n"
        f"Clanok ID: {record['id']}\n"
        f"Nazov: {record.get('title', '')}\n"
        f"Autori: {', '.join(record.get('authors', []))}\n"
        f"Rok/cislo/strany: {record.get('year')} / {record.get('issue')} / {record.get('pages')}\n\n"
        "Text extrahovany z PDF:\n"
        f"{text}"
    )


def finalize_knowledge(data: dict, record: dict, model: str, backend: str) -> dict:
    data["article_id"] = record["id"]
    data["model"] = model
    data["backend"] = backend
    data["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return data


def call_openai_api(record: dict, api_key: str, model: str, timeout: int) -> dict:
    prompt = build_knowledge_prompt(record)
    body = {
        "model": model,
        "instructions": "Vrat validny JSON podla schemy. Nevymyslaj fakty mimo dodaneho textu.",
        "input": prompt,
        "store": False,
        "max_output_tokens": 1800,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sss_article_knowledge",
                "strict": True,
                "schema": KNOWLEDGE_SCHEMA,
            }
        },
    }
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI API {response.status_code}: {response.text[:800]}")
    response_payload = response.json()
    text_payload = extract_response_text(response_payload)
    if not text_payload:
        raise RuntimeError(f"OpenAI response did not include output text: {response_payload}")
    data = json.loads(text_payload)
    return finalize_knowledge(data, record, model, "openai_api")


def call_codex(record: dict, model: str, timeout: int) -> dict:
    data = run_codex_json(build_knowledge_prompt(record), KNOWLEDGE_SCHEMA, model, timeout)
    return finalize_knowledge(data, record, model, "codex_auth")


def sync_articles_from_knowledge(knowledge_path: Path, articles_path: Path, frontend_path: Path) -> int:
    knowledge_by_id = {
        record["article_id"]: record
        for record in iter_jsonl(knowledge_path) or []
        if isinstance(record.get("article_id"), int)
    }
    if not knowledge_by_id:
        return 0

    with articles_path.open("r", encoding="utf-8") as handle:
        articles = json.load(handle)

    updated = 0
    for article in articles:
        knowledge = knowledge_by_id.get(article["id"])
        if not knowledge:
            continue
        if knowledge.get("bibliographic_abstract"):
            article["abstract"] = knowledge["bibliographic_abstract"]
        if knowledge.get("themes"):
            article["tags"] = sorted(set(article.get("tags", []) + knowledge["themes"]))
        if knowledge.get("caves"):
            article["caves"] = sorted(set(article.get("caves", []) + knowledge["caves"]))
        if knowledge.get("sss_groups"):
            article["groups"] = sorted(set(article.get("groups", []) + knowledge["sss_groups"]))
        article["knowledge"] = {
            "summary": knowledge.get("summary", ""),
            "keywords": knowledge.get("keywords", []),
            "locations": knowledge.get("locations", []),
            "people": knowledge.get("people", []),
            "confidence": knowledge.get("confidence"),
            "source": f"{knowledge.get('backend', 'openai_api')}_fulltext",
            "generated_at": knowledge.get("generated_at"),
        }
        updated += 1

    for path in (articles_path, frontend_path):
        with path.open("w", encoding="utf-8") as handle:
            json.dump(articles, handle, ensure_ascii=False, indent=2)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Use Codex auth or OpenAI API to enrich extracted article full text.")
    parser.add_argument("--input", default=str(FULLTEXT_PATH), help="Input article_fulltext JSONL.")
    parser.add_argument("--output", default=str(KNOWLEDGE_PATH), help="Output AI knowledge JSONL.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.5"), help="AI model.")
    parser.add_argument(
        "--ai-backend",
        choices=["codex", "openai"],
        default=os.environ.get("SSS_AI_BACKEND", "codex"),
        help="AI backend. Default uses saved Codex auth via `codex exec`.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process at most N articles.")
    parser.add_argument("--force", action="store_true", help="Overwrite output and reprocess existing records.")
    parser.add_argument("--sync-articles", action="store_true", help="Update articles JSON from AI knowledge output.")
    parser.add_argument("--sync-only", action="store_true", help="Only sync existing AI knowledge into articles JSON.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between OpenAI calls.")
    parser.add_argument("--timeout", type=int, default=300, help="AI call timeout seconds.")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if args.ai_backend == "openai" and not api_key and not args.sync_only:
        print("Error: OPENAI_API_KEY is required when --ai-backend openai is used.", file=sys.stderr)
        print("For Codex auth, run without that flag or use: --ai-backend codex", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.sync_only:
        updated = sync_articles_from_knowledge(output_path, ARTICLES_PATH, FRONTEND_ARTICLES_PATH)
        print(f"Synced {updated} articles from {output_path}.")
        return 0

    done_ids = set() if args.force else load_done_ids(output_path)
    mode = "w" if args.force else "a"
    processed = 0
    skipped = 0
    failed = 0

    with output_path.open(mode, encoding="utf-8") as out:
        for record in iter_jsonl(input_path) or []:
            if args.limit is not None and processed >= args.limit:
                break
            if record.get("status") != "ok" or not (record.get("text") or "").strip():
                skipped += 1
                continue
            if record["id"] in done_ids:
                skipped += 1
                continue
            try:
                if args.ai_backend == "codex":
                    enriched = call_codex(record, args.model, args.timeout)
                else:
                    enriched = call_openai_api(record, api_key, args.model, args.timeout)
                out.write(json.dumps(enriched, ensure_ascii=False) + "\n")
                out.flush()
                processed += 1
                print(f"Processed article {record['id']} via {args.ai_backend}: {record.get('title', '')[:70]}")
                time.sleep(args.sleep)
            except Exception as exc:
                if isinstance(exc, CodexAuthError):
                    print(f"Fatal Codex authentication error: {exc}", file=sys.stderr)
                    return 1
                failed += 1
                print(f"Failed article {record.get('id')}: {exc}", file=sys.stderr)

    if args.sync_articles:
        updated = sync_articles_from_knowledge(output_path, ARTICLES_PATH, FRONTEND_ARTICLES_PATH)
        print(f"Synced {updated} articles from {output_path}.")

    print(f"Done. processed={processed}, skipped={skipped}, failed={failed}, output={output_path}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
