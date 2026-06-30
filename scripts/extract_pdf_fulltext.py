#!/usr/bin/env python3
"""
Build a local full-text knowledge base from Spravodaj SSS PDF issues.

The bibliographic JSON stores article metadata and PDF URLs. This script
downloads each unique issue PDF once, extracts text for each article page
range with pdftotext, and writes article-level JSONL records.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FRONTEND_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
PDF_CACHE_DIR = BASE_DIR / "data" / "pdf_cache"
TEXT_CACHE_DIR = BASE_DIR / "data" / "pdf_text"
FULLTEXT_PATH = BASE_DIR / "data" / "article_fulltext.jsonl"
DEFAULT_PDF_PAGE_OFFSET = 2
JOURNAL_DEFAULT_PDF_PAGE_OFFSETS = {
    "aragonit": 2,
    "slovensky_kras": 0,
    "spravodaj_sss": 2,
}
DIACRITIC_CHARS = set("ÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž")
BAD_TEXT_LAYER_TOKENS = {
    "akcia",
    "bezpecnost",
    "cinnost",
    "clanku",
    "clanok",
    "clovek",
    "dalsi",
    "dalsia",
    "dalsie",
    "dedicstvo",
    "desatrocia",
    "dlzka",
    "hlbka",
    "jaskyn",
    "jaskýn",
    "jaskyna",
    "ked",
    "kolkokrat",
    "ladove",
    "ladovy",
    "moznost",
    "navstevnik",
    "navstevnikov",
    "nevyhnutnost",
    "oci",
    "opytat",
    "opýtat",
    "organizacia",
    "objavitelská",
    "pozviechat",
    "publikacna",
    "publikacná",
    "riaditel",
    "speleologicka",
    "spristupnenych",
    "sucasna",
    "sucasne",
    "sucasnost",
    "súcasná",
    "súcasne",
    "súcasnost",
    "udoli",
    "usmernuje",
    "ved",
    "velke",
    "vitazne",
    "vítazne",
    "vyhodnost",
    "výhodnost",
    "vyskumna",
    "zabezpecit",
    "zahranici",
    "zahranicne",
    "zahranicné",
    "zahranicí",
    "zivot",
}
TOKEN_RE = re.compile(r"[0-9A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž]+")


def safe_name(url: str) -> str:
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "issue.pdf"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    return f"{digest}_{stem}"


def parse_page_range(pages: str) -> tuple[int | None, int | None]:
    if not pages:
        return None, None
    cleaned = (
        str(pages)
        .replace("–", "-")
        .replace("—", "-")
        .replace(" ", "")
        .strip()
    )
    match = re.match(r"^(\d+)(?:-(\d+))?", cleaned)
    if not match:
        return None, None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if end < start:
        end = start
    return start, end


def resolve_physical_page_range(
    printed_start: int,
    printed_end: int,
    page_map: dict[int, int],
    pdf_pages: int | None = None,
) -> tuple[int | None, int | None, str | None]:
    physical_start = page_map.get(printed_start, printed_start)
    physical_end = page_map.get(printed_end, physical_start + max(printed_end - printed_start, 0))
    if physical_end < physical_start:
        physical_end = physical_start + max(printed_end - printed_start, 0)
    if pdf_pages is not None:
        if physical_start > pdf_pages:
            return None, None, "page_out_of_range"
        physical_end = min(physical_end, pdf_pages)
    return physical_start, physical_end, None


def int_or_none(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def article_pdf_page_offset(article: dict) -> int:
    journal_id = str(article.get("journal_id") or "spravodaj_sss")
    if journal_id in JOURNAL_DEFAULT_PDF_PAGE_OFFSETS and not int_or_none(article.get("pdf_page_start")):
        return JOURNAL_DEFAULT_PDF_PAGE_OFFSETS[journal_id]
    try:
        return int(article.get("pdf_page_offset"))
    except (TypeError, ValueError):
        pass
    return JOURNAL_DEFAULT_PDF_PAGE_OFFSETS.get(journal_id, DEFAULT_PDF_PAGE_OFFSET)


def has_imported_physical_pages(article: dict) -> bool:
    """Newly imported journals store physical PDF pages directly in metadata."""
    return bool(article.get("journal_id")) and int_or_none(article.get("pdf_page_start")) is not None


def resolve_article_physical_page_range(
    article: dict,
    printed_start: int,
    printed_end: int,
    page_map: dict[int, int],
    pdf_pages: int | None = None,
) -> tuple[int | None, int | None, str | None]:
    if has_imported_physical_pages(article):
        physical_start = int_or_none(article.get("pdf_page_start"))
        physical_end = int_or_none(article.get("pdf_page_end"))
        if physical_start is None:
            return None, None, "missing_page_range"
        if physical_end is None:
            physical_end = physical_start + max(printed_end - printed_start, 0)
        if physical_end < physical_start:
            physical_end = physical_start
        if pdf_pages is not None:
            if physical_start > pdf_pages:
                return None, None, "page_out_of_range"
            physical_end = min(physical_end, pdf_pages)
        return physical_start, physical_end, None

    if page_map:
        return resolve_physical_page_range(printed_start, printed_end, page_map, pdf_pages)

    offset = article_pdf_page_offset(article)
    physical_start = max(1, printed_start + offset)
    physical_end = max(physical_start, printed_end + offset)
    if pdf_pages is not None:
        if physical_start > pdf_pages:
            return None, None, "page_out_of_range"
        physical_end = min(physical_end, pdf_pages)
    return physical_start, physical_end, None


def empty_text_probe_ranges(
    physical_start: int | None,
    physical_end: int | None,
    printed_start: int,
    page_map: dict[int, int],
    pdf_pages: int | None,
    max_probe: int = 4,
) -> list[tuple[int, int]]:
    if physical_start is None or physical_end is None or printed_start in page_map:
        return []
    last_probe = physical_start + max_probe
    if pdf_pages is not None:
        last_probe = min(last_probe, pdf_pages)
    span = max(physical_end - physical_start, 0)
    ranges = []
    for probe_start in range(physical_start + 1, last_probe + 1):
        probe_end = probe_start + span
        if pdf_pages is not None:
            probe_end = min(probe_end, pdf_pages)
        ranges.append((probe_start, probe_end))
    return ranges


def normalize_search_text(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž]+", " ", value)
    return re.sub(r"\s+", " ", normalized.casefold()).strip()


def article_text_score(text: str, article: dict) -> int:
    haystack = normalize_search_text(text)
    if not haystack:
        return 0

    score = 0
    title_tokens = [
        token
        for token in normalize_search_text(article.get("title", "")).split()
        if len(token) >= 5
    ]
    for token in title_tokens[:8]:
        if token in haystack:
            score += 1

    for author in article.get("authors") or []:
        author_text = str(author)
        surname = author_text.split(",", 1)[0].strip()
        for token in normalize_search_text(surname).split():
            if len(token) >= 4 and token in haystack:
                score += 3

    abstract_tokens = [
        token
        for token in normalize_search_text(article.get("abstract", "")).split()
        if len(token) >= 6
    ]
    for token in abstract_tokens[:12]:
        if token in haystack:
            score += 1
    return score


def download_pdf(url: str, target: Path, force: bool = False) -> bool:
    if target.exists() and target.stat().st_size > 0 and not force:
        return True

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        with requests.get(url, headers=headers, stream=True, timeout=45) as response:
            if response.status_code != 200:
                print(f"  PDF download failed {response.status_code}: {url}", file=sys.stderr)
                return False
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        handle.write(chunk)
        return target.stat().st_size > 0
    except Exception as exc:
        print(f"  PDF download error for {url}: {exc}", file=sys.stderr)
        return False


def pdftotext(pdf_path: Path, first_page: int | None = None, last_page: int | None = None) -> str:
    cmd = ["pdftotext", "-layout"]
    if first_page is not None:
        cmd.extend(["-f", str(first_page)])
    if last_page is not None:
        cmd.extend(["-l", str(last_page)])
    cmd.extend([str(pdf_path), "-"])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"pdftotext failed for {pdf_path}")
    return result.stdout.strip()


def pdffonts_summary(pdf_path: Path) -> dict:
    result = subprocess.run(["pdffonts", str(pdf_path)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return {
            "status": "error",
            "error": result.stderr.strip() or f"pdffonts failed for {pdf_path}",
        }

    encodings: dict[str, int] = {}
    embedded: dict[str, int] = {}
    unicode_maps: dict[str, int] = {}
    font_rows = 0
    for line in result.stdout.splitlines():
        if not line.strip() or line.startswith("name") or line.startswith("-"):
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        font_rows += 1
        encoding = parts[-6]
        emb = parts[-5]
        uni = parts[-3]
        encodings[encoding] = encodings.get(encoding, 0) + 1
        embedded[emb] = embedded.get(emb, 0) + 1
        unicode_maps[uni] = unicode_maps.get(uni, 0) + 1

    return {
        "status": "ok",
        "font_rows": font_rows,
        "encodings": encodings,
        "embedded": embedded,
        "unicode_maps": unicode_maps,
        "all_fonts_without_unicode_map": font_rows > 0 and unicode_maps.get("no", 0) == font_rows,
    }


def text_quality_metrics(text: str) -> dict:
    tokens = TOKEN_RE.findall(text)
    bad_tokens: list[str] = []
    seen_bad: set[str] = set()
    for token in tokens:
        folded = token.casefold()
        if folded in BAD_TEXT_LAYER_TOKENS and folded not in seen_bad:
            bad_tokens.append(token)
            seen_bad.add(folded)

    return {
        "chars": len(text),
        "words": len(tokens),
        "diacritics": sum(char in DIACRITIC_CHARS for char in text),
        "bad_diacritic_token_count": len(bad_tokens),
        "bad_diacritic_token_examples": bad_tokens[:12],
    }


def should_reocr_text_layer(
    text: str,
    metrics: dict,
    font_summary: dict | None,
    min_bad_tokens: int,
    min_chars: int,
) -> tuple[bool, str]:
    if not text.strip():
        return True, "empty_text"
    if len(text) < min_chars:
        return False, "too_short_to_judge"

    bad_count = int(metrics.get("bad_diacritic_token_count") or 0)
    all_fonts_without_unicode = bool((font_summary or {}).get("all_fonts_without_unicode_map"))
    if all_fonts_without_unicode and bad_count >= min_bad_tokens:
        return True, "font_unicode_map_missing_and_bad_tokens"
    if bad_count >= min_bad_tokens * 2:
        return True, "bad_tokens"
    return False, "quality_ok"


def tesseract_language_arg(requested: str) -> tuple[str, list[str]]:
    wanted = [lang.strip() for lang in requested.split("+") if lang.strip()]
    if not wanted:
        return requested, []
    result = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return requested, []
    installed = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("List of available languages")
    }
    available = [lang for lang in wanted if lang in installed]
    missing = [lang for lang in wanted if lang not in installed]
    return "+".join(available or wanted), missing


def with_cpu_pin(command: list[str], cpu: int | None) -> list[str]:
    if cpu is None or cpu < 0 or not shutil_which("taskset"):
        return command
    return ["taskset", "-c", str(cpu), *command]


def tesseract_pdf_range(
    pdf_path: Path,
    first_page: int,
    last_page: int,
    languages: str,
    dpi: int,
    timeout: int,
    cpu: int | None,
) -> tuple[str, dict]:
    language_arg, missing_languages = tesseract_language_arg(languages)
    env = os.environ.copy()
    env["OMP_THREAD_LIMIT"] = "1"
    env["OMP_NUM_THREADS"] = "1"

    with tempfile.TemporaryDirectory(prefix="sss-ocr-") as tmp:
        prefix = Path(tmp) / "page"
        render_cmd = [
            "pdftoppm",
            "-r",
            str(dpi),
            "-png",
            "-f",
            str(first_page),
            "-l",
            str(last_page),
            str(pdf_path),
            str(prefix),
        ]
        render_result = subprocess.run(render_cmd, capture_output=True, text=True, check=False)
        if render_result.returncode != 0:
            raise RuntimeError(render_result.stderr.strip() or f"pdftoppm failed for {pdf_path}")

        page_images = sorted(prefix.parent.glob(f"{prefix.name}-*.png"))
        if not page_images:
            raise RuntimeError(f"pdftoppm produced no page images for {pdf_path}")

        page_texts: list[str] = []
        for image_path in page_images:
            cmd = with_cpu_pin(
                [
                    "tesseract",
                    str(image_path),
                    "stdout",
                    "-l",
                    language_arg,
                    "--psm",
                    "6",
                ],
                cpu,
            )
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or f"tesseract failed for {image_path}")
            page_texts.append(result.stdout.strip())

    return "\n\n".join(text for text in page_texts if text), {
        "engine": "tesseract",
        "languages": language_arg,
        "missing_languages": missing_languages,
        "dpi": dpi,
        "timeout_seconds_per_page": timeout,
        "cpu": cpu,
        "pages": len(page_texts),
        "thread_limit": 1,
    }


def choose_ocr_text(original_text: str, ocr_text: str, ocr_mode: str) -> tuple[bool, str]:
    if not ocr_text.strip():
        return False, "ocr_empty"
    if ocr_mode == "always":
        return True, "forced"
    original = text_quality_metrics(original_text)
    replacement = text_quality_metrics(ocr_text)
    original_bad = int(original.get("bad_diacritic_token_count") or 0)
    replacement_bad = int(replacement.get("bad_diacritic_token_count") or 0)
    original_words = int(original.get("words") or 0)
    replacement_words = int(replacement.get("words") or 0)
    if original_text.strip() and len(ocr_text) < max(200, int(len(original_text) * 0.55)):
        if (
            replacement_bad < original_bad
            and original_words
            and replacement_words >= max(50, int(original_words * 0.80))
        ):
            return True, "fewer_bad_tokens_with_comparable_words"
        return False, "ocr_too_short"
    if replacement_bad < original_bad:
        return True, "fewer_bad_tokens"
    if not original_text.strip():
        return True, "original_empty"
    return False, "not_better"


def pdf_page_count(pdf_path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"pdfinfo failed for {pdf_path}")
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"Cannot determine page count for {pdf_path}")


def infer_printed_page_number(text: str) -> int | None:
    """Return a standalone printed page number from page header/footer text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    footer_candidates = list(reversed(lines[-14:]))
    header_candidates = lines[:8]
    for line in footer_candidates + header_candidates:
        mixed_footer = re.search(
            r"\bSSS\s+(\d{1,4})\s+Spravodaj\b",
            line,
            flags=re.IGNORECASE,
        )
        if mixed_footer:
            return int(mixed_footer.group(1))
        match = re.match(r"^-+\s*(\d{1,4})\s*-+$", line)
        if not match:
            match = re.match(r"^(\d{1,4})$", line)
        if match:
            return int(match.group(1))
    return None


def infer_printed_page_map(pdf_path: Path, cache_path: Path, force: bool = False) -> dict[int, int]:
    """Map printed page numbers visible in the issue to physical PDF pages."""
    if cache_path.exists() and not force:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return {int(key): int(value) for key, value in cached.items()}
        except Exception:
            pass

    page_map: dict[int, int] = {}
    try:
        count = pdf_page_count(pdf_path)
    except Exception as exc:
        print(f"  Page-map inference skipped: {exc}", file=sys.stderr)
        return page_map

    for physical_page in range(1, count + 1):
        try:
            page_text = pdftotext(pdf_path, physical_page, physical_page)
        except Exception:
            continue
        printed_page = infer_printed_page_number(page_text)
        if printed_page is not None:
            page_map.setdefault(printed_page, physical_page)

    cache_path.write_text(
        json.dumps({str(key): value for key, value in sorted(page_map.items())}, indent=2),
        encoding="utf-8",
    )
    return page_map


def load_done_ids(path: Path, retry_failed: bool = False) -> set[int]:
    done: set[int] = set()
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            article_id = record.get("id")
            if retry_failed and record.get("status") != "ok":
                continue
            if isinstance(article_id, int):
                done.add(article_id)
    return done


def group_articles_by_pdf(articles: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for article in articles:
        url = (article.get("pdf_url") or "").strip()
        if not url:
            continue
        grouped.setdefault(url, []).append(article)
    return grouped


def build_record(
    article: dict,
    pdf_url: str,
    pdf_path: Path,
    text: str,
    status: str,
    physical_start: int | None = None,
    physical_end: int | None = None,
    text_source: str = "pdftotext",
    text_quality: dict | None = None,
    pdf_text_layer: dict | None = None,
    ocr: dict | None = None,
) -> dict:
    start, end = parse_page_range(article.get("pages", ""))
    record = {
        "id": article["id"],
        "title": article.get("title", ""),
        "authors": article.get("authors", []),
        "year": article.get("year"),
        "volume": article.get("volume", ""),
        "issue": article.get("issue", ""),
        "pages": article.get("pages", ""),
        "page_start": start,
        "page_end": end,
        "pdf_page_start": physical_start,
        "pdf_page_end": physical_end,
        "pdf_page_offset": article_pdf_page_offset(article),
        "pdf_url": pdf_url,
        "pdf_cache": str(pdf_path.relative_to(BASE_DIR)),
        "journal_id": article.get("journal_id") or "spravodaj_sss",
        "journal_title": article.get("journal_title") or "Spravodaj Slovenskej speleologickej spoločnosti",
        "journal_short_title": article.get("journal_short_title") or "Spravodaj SSS",
        "text": text,
        "text_chars": len(text),
        "text_source": text_source,
        "text_quality": text_quality or text_quality_metrics(text),
        "status": status,
        "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if pdf_text_layer is not None:
        record["pdf_text_layer"] = pdf_text_layer
    if ocr is not None:
        record["ocr"] = ocr
    return record


def iter_fulltext(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sync_article_page_links(fulltext_path: Path, articles_path: Path, frontend_path: Path) -> int:
    page_links: dict[int, dict] = {}
    invalid_page_links: set[int] = set()
    for record in iter_fulltext(fulltext_path) or []:
        if record.get("status") in {"ok", "empty_text"} and record.get("pdf_page_start"):
            page_links[record["id"]] = {
                "pdf_page_start": record.get("pdf_page_start"),
                "pdf_page_end": record.get("pdf_page_end"),
            }
        elif record.get("status") in {"missing_page_range", "page_out_of_range"}:
            invalid_page_links.add(record["id"])
    if not page_links and not invalid_page_links:
        return 0

    with articles_path.open("r", encoding="utf-8") as handle:
        articles = json.load(handle)

    updated = 0
    for article in articles:
        link = page_links.get(article["id"])
        if link:
            article.update(link)
            updated += 1
        elif article["id"] in invalid_page_links and (
            article.get("pdf_page_start") is not None or article.get("pdf_page_end") is not None
        ):
            article["pdf_page_start"] = None
            article["pdf_page_end"] = None
            updated += 1

    for path in (articles_path, frontend_path):
        if path.parent.exists():
            with path.open("w", encoding="utf-8") as handle:
                json.dump(articles, handle, ensure_ascii=False, indent=2)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract article full text from linked Spravodaj SSS PDFs.")
    parser.add_argument("--articles", default=str(ARTICLES_PATH), help="Path to articles JSON.")
    parser.add_argument("--output", default=str(FULLTEXT_PATH), help="JSONL output path.")
    parser.add_argument("--limit-pdfs", type=int, default=None, help="Process only first N unique PDF files.")
    parser.add_argument("--limit-articles", type=int, default=None, help="Process only first N article records.")
    parser.add_argument("--force", action="store_true", help="Re-download PDFs and re-extract existing article records.")
    parser.add_argument("--force-page-map", action="store_true", help="Rebuild printed-to-physical PDF page maps.")
    parser.add_argument("--retry-failed", action="store_true", help="Re-extract previous non-ok records without forcing all articles.")
    parser.add_argument("--no-cache-text", action="store_true", help="Do not store whole-issue text cache files.")
    parser.add_argument("--sync-articles", action="store_true", help="Write inferred PDF page links back to article JSON files.")
    parser.add_argument(
        "--ocr-mode",
        choices=("off", "bad-text", "always"),
        default="off",
        help="Optionally replace pdftotext output with safe one-CPU Tesseract OCR.",
    )
    parser.add_argument("--ocr-languages", default="slk+ces", help="Tesseract language list.")
    parser.add_argument("--ocr-dpi", type=int, default=300, help="PDF render DPI for Tesseract OCR.")
    parser.add_argument("--ocr-timeout", type=int, default=120, help="Tesseract timeout per rendered page.")
    parser.add_argument("--ocr-cpu", type=int, default=0, help="CPU core for taskset pinning; use -1 to disable.")
    parser.add_argument(
        "--ocr-min-bad-tokens",
        type=int,
        default=4,
        help="Minimum bad diacritic-token signals before OCR fallback is triggered.",
    )
    parser.add_argument(
        "--ocr-min-chars",
        type=int,
        default=600,
        help="Minimum text length before bad-layer quality heuristics are applied.",
    )
    args = parser.parse_args()

    articles_path = Path(args.articles)
    output_path = Path(args.output)
    with articles_path.open("r", encoding="utf-8") as handle:
        articles = json.load(handle)

    if not shutil_which("pdftotext"):
        print("Error: pdftotext is required but was not found on PATH.", file=sys.stderr)
        return 1
    if not shutil_which("pdfinfo"):
        print("Error: pdfinfo is required but was not found on PATH.", file=sys.stderr)
        return 1
    if args.ocr_mode != "off":
        for binary in ("pdffonts", "pdftoppm", "tesseract"):
            if not shutil_which(binary):
                print(f"Error: {binary} is required for --ocr-mode {args.ocr_mode}.", file=sys.stderr)
                return 1

    PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    done_ids = set() if args.force else load_done_ids(output_path, retry_failed=args.retry_failed)
    grouped = group_articles_by_pdf(articles)
    if not args.force:
        grouped = {
            pdf_url: [article for article in issue_articles if article.get("id") not in done_ids]
            for pdf_url, issue_articles in grouped.items()
        }
        grouped = {pdf_url: issue_articles for pdf_url, issue_articles in grouped.items() if issue_articles}
    pdf_items = list(grouped.items())
    if args.limit_pdfs is not None:
        pdf_items = pdf_items[: args.limit_pdfs]

    processed_articles = 0
    skipped_articles = 0
    failed_articles = 0

    mode = "w" if args.force else "a"
    with output_path.open(mode, encoding="utf-8") as out:
        for pdf_index, (pdf_url, issue_articles) in enumerate(pdf_items, start=1):
            pdf_name = safe_name(pdf_url)
            pdf_path = PDF_CACHE_DIR / pdf_name
            print(f"[{pdf_index}/{len(pdf_items)}] {pdf_url}")
            if not download_pdf(pdf_url, pdf_path, force=args.force):
                failed_articles += len(issue_articles)
                continue

            needs_page_map = not all(has_imported_physical_pages(article) for article in issue_articles)
            page_map = (
                infer_printed_page_map(
                    pdf_path,
                    TEXT_CACHE_DIR / f"{pdf_name}.pages.json",
                    force=args.force or args.force_page_map,
                )
                if needs_page_map
                else {}
            )
            try:
                pdf_pages = pdf_page_count(pdf_path)
            except Exception as exc:
                print(f"  PDF page count failed: {exc}", file=sys.stderr)
                pdf_pages = None
            pdf_text_layer = pdffonts_summary(pdf_path) if args.ocr_mode != "off" else None

            if not args.no_cache_text:
                text_cache = TEXT_CACHE_DIR / f"{pdf_name}.txt"
                if args.force or not text_cache.exists():
                    try:
                        text_cache.write_text(pdftotext(pdf_path), encoding="utf-8")
                    except Exception as exc:
                        print(f"  Whole-PDF text cache failed: {exc}", file=sys.stderr)

            for article in issue_articles:
                if args.limit_articles is not None and processed_articles >= args.limit_articles:
                    break
                if article["id"] in done_ids:
                    skipped_articles += 1
                    continue

                start, end = parse_page_range(article.get("pages", ""))
                if start is None:
                    record = build_record(article, pdf_url, pdf_path, "", "missing_page_range")
                    failed_articles += 1
                else:
                    physical_start, physical_end, range_error = resolve_article_physical_page_range(
                        article,
                        start,
                        end,
                        page_map,
                        pdf_pages,
                    )
                    if range_error:
                        record = build_record(article, pdf_url, pdf_path, "", range_error)
                        failed_articles += 1
                    else:
                        try:
                            text = pdftotext(pdf_path, physical_start, physical_end)
                            if not text:
                                first_non_empty: tuple[int, int, str] | None = None
                                for probe_start, probe_end in empty_text_probe_ranges(
                                    physical_start,
                                    physical_end,
                                    start,
                                    page_map,
                                    pdf_pages,
                                ):
                                    probe_text = pdftotext(pdf_path, probe_start, probe_end)
                                    if not probe_text:
                                        continue
                                    if first_non_empty is None:
                                        first_non_empty = (probe_start, probe_end, probe_text)
                                    if article_text_score(probe_text, article) > 0:
                                        physical_start = probe_start
                                        physical_end = probe_end
                                        text = probe_text
                                        break
                                if not text and first_non_empty is not None:
                                    physical_start, physical_end, text = first_non_empty
                            text_source = "pdftotext"
                            text_quality = text_quality_metrics(text)
                            ocr_meta = None
                            if args.ocr_mode != "off" and physical_start is not None and physical_end is not None:
                                if args.ocr_mode == "always":
                                    should_ocr, ocr_reason = True, "forced"
                                else:
                                    should_ocr, ocr_reason = should_reocr_text_layer(
                                        text,
                                        text_quality,
                                        pdf_text_layer,
                                        args.ocr_min_bad_tokens,
                                        args.ocr_min_chars,
                                    )
                                if should_ocr:
                                    try:
                                        ocr_text, ocr_meta = tesseract_pdf_range(
                                            pdf_path,
                                            physical_start,
                                            physical_end,
                                            args.ocr_languages,
                                            args.ocr_dpi,
                                            args.ocr_timeout,
                                            args.ocr_cpu,
                                        )
                                        use_ocr, decision = choose_ocr_text(text, ocr_text, args.ocr_mode)
                                        ocr_meta.update(
                                            {
                                                "trigger": ocr_reason,
                                                "decision": decision,
                                                "accepted": use_ocr,
                                                "quality": text_quality_metrics(ocr_text),
                                            }
                                        )
                                        if use_ocr:
                                            text = ocr_text
                                            text_source = "tesseract_ocr"
                                            text_quality = ocr_meta["quality"]
                                    except Exception as exc:
                                        ocr_meta = {
                                            "engine": "tesseract",
                                            "trigger": ocr_reason,
                                            "accepted": False,
                                            "error": str(exc),
                                        }
                            record = build_record(
                                article,
                                pdf_url,
                                pdf_path,
                                text,
                                "ok" if text else "empty_text",
                                physical_start,
                                physical_end,
                                text_source=text_source,
                                text_quality=text_quality,
                                pdf_text_layer=pdf_text_layer,
                                ocr=ocr_meta,
                            )
                        except Exception as exc:
                            print(f"  Article {article['id']} extraction failed: {exc}", file=sys.stderr)
                            record = build_record(
                                article,
                                pdf_url,
                                pdf_path,
                                "",
                                "pdftotext_failed",
                                physical_start,
                                physical_end,
                                pdf_text_layer=pdf_text_layer,
                            )
                            failed_articles += 1

                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                processed_articles += 1

            if args.limit_articles is not None and processed_articles >= args.limit_articles:
                break

    synced = 0
    if args.sync_articles:
        synced = sync_article_page_links(output_path, ARTICLES_PATH, FRONTEND_ARTICLES_PATH)

    print(
        "Done. "
        f"processed={processed_articles}, skipped={skipped_articles}, failed={failed_articles}, "
        f"synced={synced}, output={output_path}"
    )
    return 0


def shutil_which(binary: str) -> str | None:
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(entry) / binary
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
