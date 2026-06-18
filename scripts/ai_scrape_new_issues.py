#!/usr/bin/env python3
"""
Codex/OpenAI scraper for new issues of Spravodaj SSS.

Scrapes sss.sk for new PDFs, extracts table-of-contents text with pdftotext,
uses Codex auth or OpenAI Structured Outputs to parse article metadata, and appends records
to the local bibliography / optional Zotero library.
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from codex_ai_backend import CodexAuthError, run_codex_json


SSS_INDEX_URL = "https://sss.sk/spravodaj/"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FRONTEND_DB_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
URL_MAP_PATH = BASE_DIR / "data" / "urls_map.json"


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
                },
                "required": ["title", "authors", "pages", "extras", "abstract"],
            },
        }
    },
    "required": ["articles"],
}


def scrape_pdf_links() -> list[tuple[str, str]]:
    """Scrape sss.sk/spravodaj/ for PDF links and visible link text."""
    print(f"Scraping {SSS_INDEX_URL} for new PDFs...")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(SSS_INDEX_URL, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        print(f"Error scraping website: {exc}", file=sys.stderr)
        return []

    link_pattern = re.compile(
        r'<a[^>]+href="([^"]+uploads/[^"]+\.pdf)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    matches = [
        (url, re.sub(r"<[^>]+>", "", text).strip())
        for url, text in link_pattern.findall(response.text)
    ]
    print(f"Found {len(matches)} PDF links on the page.")
    return matches


def normalize_issue(issue: str) -> str:
    issue = str(issue or "").strip().lower().replace(" ", "")
    if issue in {"kongres", "mimoriadne"}:
        return issue
    return issue.replace("_", "-")


def parse_issue_key(issue_key: str, url: str) -> dict | None:
    match = re.fullmatch(r"(19\d\d|20\d\d)_(.+)", str(issue_key or "").strip())
    if not match:
        return None
    year = int(match.group(1))
    issue = normalize_issue(match.group(2))
    if not issue:
        return None
    return {
        "year": year,
        "issue": issue,
        "pdf_url": url,
        "key": f"{year}_{issue}",
    }


def pdf_filename(url: str) -> str:
    return unquote(Path(urlparse(url).path).name or "")


def parse_issue_from_filename(url: str) -> tuple[int, str] | None:
    filename = pdf_filename(url)
    stem = Path(filename).stem
    lowered = stem.lower()

    short_spravodajca = re.fullmatch(r"sp(9[2-9])([1-4])", lowered)
    if short_spravodajca:
        return int(f"19{short_spravodajca.group(1)}"), normalize_issue(short_spravodajca.group(2))

    year_matches = [int(value) for value in re.findall(r"(?:19|20)\d{2}", stem)]
    if not year_matches:
        return None

    year = year_matches[-1]
    if "kongres" in lowered:
        return year, "kongres"
    if "mimoriadne" in lowered:
        return year, "mimoriadne"

    issue_token = r"([1-4](?:[-_+][1-4])?)"
    issue_patterns = [
        rf"(?:^|[^0-9]){issue_token}[^0-9]+{year}(?:[^0-9]|$)",
        rf"(?:^|[^0-9]){year}[^0-9]+{issue_token}(?:[^0-9]|$)",
    ]
    for pattern in issue_patterns:
        match = re.search(pattern, stem)
        if match:
            return year, normalize_issue(match.group(1))
    if "jaskyniar" in lowered:
        return year, "1"
    return None


def issue_from_text_or_filename(link_text: str, url: str, lowered: str) -> str:
    clean = re.sub(
        r"\b(19\d\d|20\d\d|Spravodajca|Spravodaj|Jaskyniar|Bulletin|Slovak|Speleological|Society)\b",
        "",
        link_text,
        flags=re.IGNORECASE,
    )
    clean = clean.replace("-", " ").replace("_", " ").replace("+", " ").replace("/", " ").strip()
    digits = re.findall(r"\d+", clean)
    if len(digits) == 1:
        return digits[0]
    if len(digits) >= 2:
        return f"{digits[0]}-{digits[1]}"

    filename = pdf_filename(url)
    file_digits = re.findall(r"\d+", Path(filename).stem)
    if file_digits:
        issue = file_digits[0]
        if len(issue) == 3:
            return issue[2:]
        if issue in {"1", "2", "3", "4"}:
            return issue

    if "kongres" in lowered:
        return "kongres"
    if "mimoriadne" in lowered:
        return "mimoriadne"
    return "1"


def parse_link_info(link_text: str, url: str, issue_key: str | None = None) -> dict | None:
    """Normalize link text and URL to extract year and issue."""
    text = link_text.strip()
    lowered = f"{text} {url}".lower()
    if "bibliografia" in lowered or "b17" in lowered:
        return None

    if issue_key:
        keyed = parse_issue_key(issue_key, url)
        if keyed:
            return keyed

    filename_info = parse_issue_from_filename(url)
    if filename_info:
        year, issue = filename_info
        return {
            "year": year,
            "issue": issue,
            "pdf_url": url,
            "key": f"{year}_{issue}",
        }

    year_match = re.search(r"\b(20\d\d|19\d\d)\b", text)
    if year_match:
        year = int(year_match.group(1))
    else:
        upload_match = re.search(r"/uploads/(\d{4})/", url)
        if not upload_match:
            return None
        year = int(upload_match.group(1))

    issue = issue_from_text_or_filename(text, url, lowered)

    if "kongres" in lowered:
        issue = "kongres"
    elif "mimoriadne" in lowered:
        issue = "mimoriadne"

    return {
        "year": year,
        "issue": issue,
        "pdf_url": url,
        "key": f"{year}_{issue}",
    }


def issue_sort_key(info: dict) -> tuple[int, int, str]:
    issue = str(info.get("issue") or "")
    match = re.match(r"\d+", issue)
    issue_order = int(match.group(0)) if match else 99
    return int(info.get("year") or 0), issue_order, issue


def load_url_map(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected an object in {path}")
    return {str(key): str(value) for key, value in data.items()}


def existing_issue_keys(articles: list[dict]) -> set[str]:
    return {f"{article['year']}_{normalize_issue(article['issue'])}" for article in articles}


def missing_issue_infos_from_url_map(
    url_map: dict[str, str],
    existing_articles: list[dict],
    include_keys: set[str] | None = None,
    key_regex: str | None = None,
) -> list[dict]:
    processed_issues = existing_issue_keys(existing_articles)
    compiled = re.compile(key_regex) if key_regex else None
    missing: list[dict] = []
    seen: set[str] = set()

    for issue_key, url in url_map.items():
        if include_keys and issue_key not in include_keys:
            continue
        if compiled and not compiled.search(issue_key):
            continue
        info = parse_link_info(issue_key, url, issue_key=issue_key)
        if not info:
            continue
        if info["key"] in processed_issues or info["key"] in seen:
            continue
        missing.append(info)
        seen.add(info["key"])

    return sorted(missing, key=issue_sort_key)


def extract_pdf_toc(pdf_url: str, max_pages: int = 8) -> str | None:
    """Download a PDF and extract its first pages, where the TOC usually lives."""
    print(f"Downloading TOC pages from {pdf_url}...")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    temp_pdf_path = None
    try:
        response = requests.get(pdf_url, headers=headers, stream=True, timeout=45)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    temp_pdf.write(chunk)
            temp_pdf_path = temp_pdf.name

        print(f"  Running pdftotext on first {max_pages} pages...")
        cmd = ["pdftotext", "-layout", "-f", "1", "-l", str(max_pages), temp_pdf_path, "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except Exception as exc:
        print(f"  Error extracting TOC from PDF: {exc}", file=sys.stderr)
        return None
    finally:
        if temp_pdf_path:
            try:
                os.unlink(temp_pdf_path)
            except OSError:
                pass


def extract_response_text(payload: dict) -> str:
    if payload.get("output_text"):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks).strip()


def build_toc_prompt(toc_text: str) -> str:
    return (
        "Analyzuj text obsahu (TOC) zo slovenského jaskyniarskeho časopisu Spravodaj SSS. "
        "Extrahuj iba skutočné články/príspevky z obsahu, nie reklamy ani navigačný text. "
        "Autori majú byť vo formáte 'Priezvisko, M.'; pri anonymných/redakčných príspevkoch použi "
        "'Anonymus' alebo 'Redakcia'. Strany zapisuj ako '12-15' alebo '6'. "
        "Extras obsahuje skratky ako '4 obr.', '1 pl. j.', 'lit.', 'res.', ak sú uvedené. "
        "Abstract má byť krátka vecná anotácia v štýle bibliografie, nie kreatívne zhrnutie. "
        "Vráť iba JSON podľa požadovanej schémy.\n\n"
        f"TEXT OBSAHU:\n{toc_text[:24000]}"
    )


def extract_articles_with_codex(toc_text: str, model: str, timeout: int) -> list[dict] | None:
    """Use Codex CLI auth to parse TOC text into article records."""
    print(f"Querying Codex model {model} for structured article extraction...")
    try:
        data = run_codex_json(build_toc_prompt(toc_text), ARTICLE_SCHEMA, model, timeout)
        return data.get("articles", [])
    except CodexAuthError:
        raise
    except Exception as exc:
        print(f"  Error parsing Codex response: {exc}", file=sys.stderr)
        return None


def extract_articles_with_openai(toc_text: str, api_key: str, model: str, timeout: int) -> list[dict] | None:
    """Use OpenAI Structured Outputs to parse TOC text into article records."""
    print(f"Querying OpenAI model {model} for structured article extraction...")
    prompt = build_toc_prompt(toc_text)
    body = {
        "model": model,
        "instructions": (
            "Si konzervatívny bibliograf. Výstup musí byť validný JSON podľa schémy. "
            "Nevymýšľaj články, autorov, strany ani anotácie mimo dodaného textu."
        ),
        "input": prompt,
        "store": False,
        "max_output_tokens": 4000,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sss_issue_articles",
                "strict": True,
                "schema": ARTICLE_SCHEMA,
            }
        },
    }
    try:
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
            print(f"  OpenAI API error {response.status_code}: {response.text[:800]}", file=sys.stderr)
            return None
        data = json.loads(extract_response_text(response.json()))
        return data.get("articles", [])
    except Exception as exc:
        print(f"  Error parsing OpenAI response: {exc}", file=sys.stderr)
        return None


def normalize_pages(pages: str) -> str:
    return (
        str(pages)
        .strip()
        .replace(" – ", "-")
        .replace("–", "-")
        .replace(" ", "")
    )


def copy_to_frontend(articles: list[dict]) -> None:
    if FRONTEND_DB_PATH.parent.exists():
        with FRONTEND_DB_PATH.open("w", encoding="utf-8") as handle:
            json.dump(articles, handle, ensure_ascii=False, indent=2)
        print(f"  Copied updated database to Astro data store: {FRONTEND_DB_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex/OpenAI scraper for new Spravodaj SSS issues")
    parser.add_argument("--limit-issues", type=int, default=None, help="Limit number of new issues to process")
    parser.add_argument("--toc-pages", type=int, default=8, help="Number of first PDF pages to extract")
    parser.add_argument("--from-url-map", action="store_true", help="Process missing issues from data/urls_map.json instead of scraping the live page.")
    parser.add_argument("--url-map", default=str(URL_MAP_PATH), help="Issue URL map used with --from-url-map.")
    parser.add_argument("--issue-key", action="append", default=None, help="Process only this URL-map issue key. Can be repeated.")
    parser.add_argument("--issue-key-regex", default=None, help="Process only URL-map issue keys matching this regex.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.5"), help="AI model")
    parser.add_argument(
        "--ai-backend",
        choices=["codex", "openai"],
        default=os.environ.get("SSS_AI_BACKEND", "codex"),
        help="AI backend. Default uses saved Codex auth via `codex exec`.",
    )
    parser.add_argument("--timeout", type=int, default=300, help="AI call timeout seconds")
    args = parser.parse_args()

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if args.ai_backend == "openai" and not openai_api_key:
        print("Error: OPENAI_API_KEY is required when --ai-backend openai is used.", file=sys.stderr)
        print("For Codex auth, run without that flag or use: --ai-backend codex", file=sys.stderr)
        return 1

    if not DB_PATH.exists():
        print(f"Error: Local database not found at {DB_PATH}", file=sys.stderr)
        return 1

    with DB_PATH.open("r", encoding="utf-8") as handle:
        existing_articles = json.load(handle)

    max_id = max(article["id"] for article in existing_articles)
    print(f"Current database: {len(existing_articles)} articles, highest ID {max_id}.")

    if args.from_url_map:
        url_map = load_url_map(Path(args.url_map))
        new_issues = missing_issue_infos_from_url_map(
            url_map,
            existing_articles,
            include_keys=set(args.issue_key) if args.issue_key else None,
            key_regex=args.issue_key_regex,
        )
    else:
        processed_issues = existing_issue_keys(existing_articles)
        new_issues: list[dict] = []
        for url, link_text in scrape_pdf_links():
            info = parse_link_info(link_text, url)
            if info and info["key"] not in processed_issues and not any(item["key"] == info["key"] for item in new_issues):
                new_issues.append(info)
        new_issues = sorted(new_issues, key=issue_sort_key)

    if args.limit_issues is not None:
        new_issues = new_issues[: args.limit_issues]

    print(f"Found {len(new_issues)} new issues to process.")
    for issue in new_issues:
        print(f"  - {issue['key']}: {issue['pdf_url']}")

    new_extracted_total = 0
    for issue in new_issues:
        print(f"\nProcessing issue {issue['key']}...")
        toc_text = extract_pdf_toc(issue["pdf_url"], args.toc_pages)
        if not toc_text or not toc_text.strip():
            print("  Empty TOC text, skipping.", file=sys.stderr)
            continue

        if args.ai_backend == "codex":
            try:
                parsed_articles = extract_articles_with_codex(toc_text, args.model, args.timeout)
            except CodexAuthError as exc:
                print(f"Fatal Codex authentication error: {exc}", file=sys.stderr)
                return 1
        else:
            parsed_articles = extract_articles_with_openai(toc_text, openai_api_key, args.model, args.timeout)
        if not parsed_articles:
            print("  No articles extracted.", file=sys.stderr)
            continue

        issue_articles = []
        for parsed in parsed_articles:
            max_id += 1
            issue_articles.append(
                {
                    "id": max_id,
                    "authors": parsed.get("authors") or ["Anonymus"],
                    "title": parsed.get("title", "").strip(),
                    "pages": normalize_pages(parsed.get("pages", "")),
                    "extras": parsed.get("extras") or [],
                    "year": issue["year"],
                    "volume": "",
                    "issue": issue["issue"],
                    "abstract": parsed.get("abstract", "").strip(),
                    "pdf_url": issue["pdf_url"],
                    "caves": [],
                    "tags": [],
                    "groups": [],
                    "wikidata": [],
                    "created_by": f"{args.ai_backend}_structured_toc",
                    "created_at": dt.datetime.now(dt.UTC).isoformat(),
                }
            )

        existing_articles.extend(issue_articles)
        new_extracted_total += len(issue_articles)
        with DB_PATH.open("w", encoding="utf-8") as handle:
            json.dump(existing_articles, handle, ensure_ascii=False, indent=2)
        copy_to_frontend(existing_articles)
        print(f"  Added {len(issue_articles)} articles from issue {issue['key']}.")

        api_key = os.environ.get("ZOTERO_API_KEY")
        library_id = os.environ.get("ZOTERO_LIBRARY_ID")
        if api_key and library_id:
            print("  Zotero credentials found. Uploading this issue...")
            from upload_to_zotero import build_zotero_item, upload_batch

            zotero_items = [build_zotero_item(article) for article in issue_articles]
            total_uploaded = 0
            for idx in range(0, len(zotero_items), 50):
                total_uploaded += upload_batch(library_id, "group", api_key, zotero_items[idx : idx + 50])
            print(f"  Uploaded {total_uploaded} Zotero items.")

        time.sleep(0.2)

    print(f"\nAI scrape completed via {args.ai_backend}. Total new articles added: {new_extracted_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
