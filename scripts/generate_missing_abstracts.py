#!/usr/bin/env python3
"""Generate missing bibliographic abstracts from article PDF text.

Default scope is intentionally narrow: records imported by
scripts/import_latest_journal_samples.py with empty or generic abstracts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

import requests

import extract_pdf_fulltext as fulltext


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
DEFAULT_FRONTEND_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
DEFAULT_MODEL = "gemma4:e2b-it-qat"
SAMPLE_IMPORT_CREATED_BY = "codex_journal_sample_import"
MAX_TEXT_CHARS = 9000
MAX_ABSTRACT_CHARS = 420
OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"

GENERIC_IMPORT_RE = re.compile(
    r"\bObsahový\s+záznam\s+z\s+čísla\b.*\bimportovaný\s+z\s+obsahu\s+čísla\b",
    flags=re.IGNORECASE,
)
BAD_EMPTY_RE = re.compile(
    r"^(?:empty|n/?a|neviem|nedá sa|neda sa|bez anotácie|bez anotacie|"
    r"nie je k dispozícii|nie je k dispozicii|nemám dostatok|nemam dostatok)\b",
    flags=re.IGNORECASE,
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_generic_import_abstract(value: str) -> bool:
    text = normalize_spaces(value)
    return bool(text and GENERIC_IMPORT_RE.search(text))


def select_candidate_articles(
    articles: list[dict[str, Any]],
    *,
    imported_only: bool = True,
    force: bool = False,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for article in articles:
        if imported_only and article.get("created_by") != SAMPLE_IMPORT_CREATED_BY:
            continue
        if force:
            candidates.append(article)
            continue
        abstract = normalize_spaces(article.get("abstract") or "")
        if not abstract or is_generic_import_abstract(abstract) or article.get("abstract_source") == "missing":
            candidates.append(article)
    return candidates


def safe_title_abstract(article: dict[str, Any]) -> str:
    title = normalize_spaces(article.get("title") or "")
    if not title:
        return ""

    title = title.rstrip(".")
    folded = title.casefold()
    if "projekt" in folded:
        prefix = "Príspevok informuje o projekte"
    elif "konferencia" in folded or "convention" in folded or "kongres" in folded:
        prefix = "Správa z podujatia"
    elif folded.startswith(("k ", "ku ")):
        prefix = "Príspevok pripomína"
    elif "vzpomínka" in folded or "spomienk" in folded:
        prefix = "Spomienkový príspevok"
    elif "map" in folded:
        prefix = "Príspevok sa venuje mapovým podkladom a téme"
    else:
        prefix = "Príspevok sa venuje téme"

    return concise_sentences(f"{prefix} „{title}“.")


def concise_sentences(text: str, max_sentences: int = 2, max_chars: int = MAX_ABSTRACT_CHARS) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    if sentences:
        text = normalize_spaces(" ".join(sentences[:max_sentences]))
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "."


def normalize_generated_abstract(value: str) -> str:
    text = normalize_spaces(value)
    done_thinking = re.search(r"\.\.\.\s*done\s+thinking\.?", text, flags=re.IGNORECASE)
    if done_thinking:
        text = normalize_spaces(text[done_thinking.end() :])
    marker = re.search(r"\bANOT[ÁA]CIA\s*:\s*", text, flags=re.IGNORECASE)
    if marker:
        text = normalize_spaces(text[marker.end() :])
    text = re.sub(r"^Thinking\.\.\..*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = text.strip("`'\" \t\r\n")
    text = re.sub(r"^(?:[-*]\s*)?(?:ANOT[ÁA]CIA|Anotácia|Anotacia|Bibliografická anotácia|Bibliograficka anotacia|Abstrakt)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    text = normalize_spaces(text)

    if not text or is_generic_import_abstract(text) or BAD_EMPTY_RE.search(text):
        return ""
    if len(text) < 25:
        return ""
    return concise_sentences(text)


def int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def article_physical_page_range(article: dict[str, Any]) -> tuple[int | None, int | None]:
    start = int_or_none(article.get("pdf_page_start"))
    end = int_or_none(article.get("pdf_page_end"))
    if start is None:
        printed_start, printed_end = fulltext.parse_page_range(str(article.get("pages") or ""))
        if printed_start is None:
            return None, None
        offset = int_or_none(article.get("pdf_page_offset")) or 0
        start = printed_start + offset
        end = (printed_end or printed_start) + offset
    if end is None or end < start:
        end = start
    return max(1, start), max(1, end)


def extract_article_text(
    article: dict[str, Any],
    *,
    offline: bool = False,
    force_download: bool = False,
) -> str:
    url = str(article.get("pdf_url") or "").strip()
    if not url:
        return ""
    start, end = article_physical_page_range(article)
    if start is None or end is None:
        return ""

    fulltext.PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = fulltext.PDF_CACHE_DIR / fulltext.safe_name(url)
    if not pdf_path.exists() or force_download:
        if offline:
            return ""
        if not fulltext.download_pdf(url, pdf_path, force=force_download):
            return ""

    try:
        page_count = fulltext.pdf_page_count(pdf_path)
        if start > page_count:
            return ""
        end = min(end, page_count)
        return fulltext.pdftotext(pdf_path, start, end)
    except Exception as exc:
        print(f"PDF text extraction failed for article {article.get('id')}: {exc}", file=sys.stderr)
        return ""


def build_prompt(article: dict[str, Any], text: str) -> str:
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n\n[TEXT SKRATENY PRE KONTEXT]"

    authors = ", ".join(article.get("authors") or [])
    journal = article.get("journal_title") or article.get("journal_short_title") or "speleologický časopis"
    return (
        "Si odborný bibliograf a speleologický redaktor. "
        "Z dodaného textu článku vytvor jednu vecnú slovenskú anotáciu pre bibliografiu. "
        "Maximálne 1-2 vety a 360 znakov. Použi jednoduchú slovenčinu a terminológiu zo slovenského názvu článku. "
        "Zachovaj konkrétne jaskyne, lokality, metódy a výsledky, "
        "ak sú v texte uvedené. Nevymýšľaj fakty mimo textu. "
        "Nemeň vlastné názvy lokalít do neistej gramatiky; radšej napíš názov v základnom tvare. "
        "Nepíš rozmery ani technické údaje, ak si nie si istý ich významom. "
        "Ak text nestačí na vecnú anotáciu, odpovedz iba slovom EMPTY. "
        "Neuvažuj nahlas a nepíš postup. Výstup musí byť presne jeden riadok vo formáte: "
        "ANOTACIA: <text anotácie>.\n\n"
        f"Názov: {article.get('title', '')}\n"
        f"Autori: {authors}\n"
        f"Časopis: {journal}\n"
        f"Rok/číslo/strany: {article.get('year')} / {article.get('issue')} / {article.get('pages')}\n\n"
        "Text z PDF:\n"
        f"{text}"
    )


def run_ollama_abstract(
    article: dict[str, Any],
    text: str,
    *,
    model: str,
    timeout: int,
) -> str:
    prompt = build_prompt(article, text)
    response = requests.post(
        OLLAMA_GENERATE_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {
                "num_predict": 180,
                "temperature": 0.1,
                "top_p": 0.9,
            },
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Ollama API {response.status_code}: {response.text[:500]}")
    payload = response.json()
    return normalize_generated_abstract(payload.get("response") or "")


def generate_abstract_for_article(
    article: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 240,
    offline: bool = False,
    force_download: bool = False,
) -> str:
    text = extract_article_text(article, offline=offline, force_download=force_download)
    if not normalize_spaces(text):
        return ""
    return run_ollama_abstract(article, text, model=model, timeout=timeout)


def apply_abstract_result(
    article: dict[str, Any],
    generated: str,
    *,
    model: str,
    generated_at: str,
    source: str = "ai_pdf_text",
) -> bool:
    normalized = normalize_generated_abstract(generated)
    old_abstract = normalize_spaces(article.get("abstract") or "")
    old_source = article.get("abstract_source")

    if normalized:
        article["abstract"] = normalized
        article["abstract_source"] = source
        article["abstract_generated_by"] = model
        article["abstract_generated_at"] = generated_at
        article.pop("abstract_generation_error", None)
        return normalize_spaces(article.get("abstract") or "") != old_abstract or old_source != source

    if not old_abstract or is_generic_import_abstract(old_abstract):
        changed = bool(old_abstract) or article.get("abstract_source") != "missing"
        article["abstract"] = ""
        article["abstract_source"] = "missing"
        article.pop("abstract_generated_by", None)
        article.pop("abstract_generated_at", None)
        return changed
    return False


def read_articles(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_articles(path: Path, articles: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_generated_abstracts(
    *,
    articles_path: Path,
    frontend_path: Path,
    generator: Callable[[dict[str, Any]], str],
    model: str,
    limit: int | None,
    imported_only: bool = True,
    force: bool = False,
    source: str = "ai_pdf_text",
) -> dict[str, int]:
    articles = read_articles(articles_path)
    candidates = select_candidate_articles(articles, imported_only=imported_only, force=force)
    if limit is not None:
        candidates = candidates[:limit]

    processed = 0
    updated = 0
    failed = 0
    generated_at = utc_now()

    for article in candidates:
        processed += 1
        try:
            generated = generator(article)
        except Exception as exc:
            failed += 1
            generated = ""
            article["abstract_generation_error"] = str(exc)[:500]
            print(f"Article {article.get('id')} abstract generation failed: {exc}", file=sys.stderr)
        else:
            if not normalize_generated_abstract(generated):
                failed += 1

        if apply_abstract_result(article, generated, model=model, generated_at=generated_at, source=source):
            updated += 1

    if updated:
        write_articles(articles_path, articles)
        write_articles(frontend_path, articles)

    return {
        "candidates": len(select_candidate_articles(articles, imported_only=imported_only, force=force)),
        "processed": processed,
        "updated": updated,
        "failed": failed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--frontend", type=Path, default=DEFAULT_FRONTEND_PATH)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--check", action="store_true", help="Show candidates without changing files.")
    parser.add_argument("--all", action="store_true", help="Include all articles with missing/generic abstracts, not only sample imports.")
    parser.add_argument("--offline", action="store_true", help="Use only already cached PDFs.")
    parser.add_argument("--force-download", action="store_true", help="Re-download PDFs even when cached.")
    parser.add_argument("--force", action="store_true", help="Regenerate matching records even when an abstract already exists.")
    parser.add_argument("--title-fallback", action="store_true", help="Use conservative title-derived abstracts instead of AI.")
    parser.add_argument("--no-ai", action="store_true", help="Only clear generic placeholders and mark abstracts as missing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    articles = read_articles(args.articles)
    candidates = select_candidate_articles(articles, imported_only=not args.all, force=args.force)
    selected = candidates[: args.limit] if args.limit is not None else candidates
    if args.check:
        summary = {
            "source": str(args.articles),
            "candidates": len(candidates),
            "selected": len(selected),
            "imported_only": not args.all,
            "ids": [article.get("id") for article in selected],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    abstract_source = "ai_pdf_text"
    if args.title_fallback:
        generator = safe_title_abstract
        abstract_source = "title_fallback"
    elif args.no_ai:
        generator = lambda article: ""
        abstract_source = "missing"
    else:
        generator = lambda article: generate_abstract_for_article(
            article,
            model=args.model,
            timeout=args.timeout,
            offline=args.offline,
            force_download=args.force_download,
        )

    summary = sync_generated_abstracts(
        articles_path=args.articles,
        frontend_path=args.frontend,
        generator=generator,
        model=args.model,
        limit=args.limit,
        imported_only=not args.all,
        force=args.force,
        source=abstract_source,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
