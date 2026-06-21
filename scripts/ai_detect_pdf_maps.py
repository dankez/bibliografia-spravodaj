#!/usr/bin/env python3
"""AI-only visual map/plan detection for one Spravodaj SSS issue PDF.

This script intentionally avoids text heuristics. It renders PDF pages to
images, asks a local Ollama vision model to inspect each image, and stores the
result in a separate test artifact. It does not modify article JSON files.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FULLTEXT_PATH = BASE_DIR / "data" / "article_fulltext.jsonl"
OUTPUT_DIR = BASE_DIR / "data" / "ai_map_detection"
DEFAULT_MODEL = "granite3.2-vision:latest"

PROMPT = """You are visually inspecting one rendered PDF page from a Slovak caving journal.
Use ONLY visible image content. Do not infer from an article title, metadata, or likely context.

Return only strict JSON:
{
  "map_plan": true,
  "page_type": "technical_map_page",
  "kind": "cave_plan",
  "confidence": "high",
  "visual_evidence": ["visible scale bar", "technical line drawing of cave passages"],
  "reject_reason": "",
  "contains_photo": false,
  "contains_table": false
}

Set "map_plan": true ONLY when the page visibly contains a cave map, cave plan, floor plan,
survey drawing, cross-section/profile, technical line drawing of cave passages, legend, scale,
or measured speleological diagram.

Set "map_plan": false for ordinary text pages, covers, author lists, photographs, tables,
charts, diagrams that are not maps/plans, and administrative phrases like a plan of work.
Full-page cave photographs, cover photos, cave-diver photos, logos, speleologists, and cave
interior photos are NOT maps/plans even if they show a cave.
Topographic terrain maps, shaded relief maps, landscape overview maps, or broad locality maps
with cave labels are NOT map_plan unless visible cave passages, cave survey linework, a cave
profile, or a measured cave cross-section are clearly drawn.

Allowed "page_type" values: "cover", "photo_page", "text_page", "table_page",
"technical_map_page", "mixed_article_map", "other".
Allowed "kind" values: "cave_plan", "cross_section", "survey_diagram", "terrain_location_map", "not_map".
Allowed "confidence" values: "low", "medium", "high".
Keep evidence short and visual, not textual speculation.
"""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)
    fsync_parent(path)


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


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for record in sorted(records, key=lambda item: int(item["page"])):
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)
    fsync_parent(path)


def fsync_parent(path: Path) -> None:
    """Best-effort directory fsync so crash recovery sees renamed files."""
    try:
        fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def issue_key(issue: Any) -> str:
    return str(issue).strip()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def load_issue_articles(year: int, issue: str) -> list[dict[str, Any]]:
    articles = read_json(ARTICLES_PATH)
    selected = [
        article
        for article in articles
        if int(article.get("year") or 0) == year and issue_key(article.get("issue")) == issue
    ]
    if not selected:
        raise RuntimeError(f"No articles found for {year}/{issue}.")
    return selected


def load_issue_fulltext(year: int, issue: str) -> list[dict[str, Any]]:
    return [
        record
        for record in iter_jsonl(FULLTEXT_PATH) or []
        if int(record.get("year") or 0) == year and issue_key(record.get("issue")) == issue
    ]


def resolve_pdf_path(records: list[dict[str, Any]], articles: list[dict[str, Any]]) -> tuple[Path, str]:
    for record in records:
        cache = record.get("pdf_cache")
        if not cache:
            continue
        path = Path(str(cache))
        if not path.is_absolute():
            path = BASE_DIR / path
        if path.exists():
            return path, str(record.get("pdf_url") or "")

    pdf_url = next((str(article.get("pdf_url")) for article in articles if article.get("pdf_url")), "")
    raise RuntimeError(f"No cached PDF found for issue. PDF URL: {pdf_url or 'unknown'}")


def pdf_page_count(pdf_path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"pdfinfo failed for {pdf_path}")
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"Cannot determine PDF page count for {pdf_path}")


def render_pdf_page(pdf_path: Path, page: int, render_dir: Path, dpi: int) -> Path:
    if not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm is not available.")
    render_dir.mkdir(parents=True, exist_ok=True)
    prefix = render_dir / f"{pdf_path.stem}_p{page}"
    output = Path(f"{prefix}.png")
    if output.exists():
        if output.stat().st_size > 0:
            return output
        output.unlink()
    tmp_prefix = render_dir / f".{prefix.name}.tmp-{os.getpid()}"
    tmp_output = Path(f"{tmp_prefix}.png")
    if tmp_output.exists():
        tmp_output.unlink()
    result = subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-singlefile",
            "-png",
            "-r",
            str(dpi),
            str(pdf_path),
            str(tmp_prefix),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not tmp_output.exists() or tmp_output.stat().st_size == 0:
        if tmp_output.exists():
            tmp_output.unlink()
        raise RuntimeError(result.stderr.strip() or f"pdftoppm failed for page {page}")
    tmp_output.replace(output)
    fsync_parent(output)
    return output


def extract_json_object(content: str) -> dict[str, Any]:
    clean = content.strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I | re.S).strip()
    match = re.search(r"\{.*\}", clean, flags=re.S)
    if not match:
        return {"parse_error": "no_json_object", "raw": content[:1000]}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return {"parse_error": str(exc), "raw": content[:1000]}


def normalize_ai_response(response: dict[str, Any]) -> dict[str, Any]:
    page_type = str(response.get("page_type") or "other").strip()
    allowed_page_types = {
        "cover",
        "photo_page",
        "text_page",
        "table_page",
        "technical_map_page",
        "mixed_article_map",
        "other",
    }
    if page_type not in allowed_page_types:
        page_type = "other"
    kind = str(response.get("kind") or "not_map").strip()
    if kind not in {"cave_plan", "cross_section", "survey_diagram", "terrain_location_map", "not_map"}:
        kind = "not_map"
    confidence = str(response.get("confidence") or "low").strip().casefold()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    evidence = response.get("visual_evidence")
    if not isinstance(evidence, list):
        evidence = []
    evidence = [str(item).strip() for item in evidence if str(item).strip()][:5]
    map_page_type = page_type in {"technical_map_page", "mixed_article_map"}
    map_kind = kind in {"cave_plan", "cross_section", "survey_diagram"}
    map_plan = bool(response.get("map_plan")) and map_kind and map_page_type
    return {
        "map_plan": map_plan,
        "page_type": page_type,
        "kind": kind if map_plan else "not_map",
        "confidence": confidence,
        "visual_evidence": evidence,
        "reject_reason": str(response.get("reject_reason") or "").strip(),
        "contains_photo": bool(response.get("contains_photo")),
        "contains_table": bool(response.get("contains_table")),
        "parse_error": response.get("parse_error"),
        "raw": response.get("raw"),
    }


def classify_image(image_path: Path, model: str, timeout: int, ollama_url: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": PROMPT,
                "images": [base64.b64encode(image_path.read_bytes()).decode("ascii")],
            }
        ],
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        ollama_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return normalize_ai_response({"parse_error": f"ollama_error: {exc}", "raw": ""})

    content = ((body.get("message") or {}).get("content") or body.get("response") or "").strip()
    return normalize_ai_response(extract_json_object(content))


def articles_for_page(page: int, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    for article in articles:
        start = article.get("pdf_page_start")
        end = article.get("pdf_page_end") or start
        if start is None:
            continue
        try:
            if int(start) <= page <= int(end):
                matches.append(article)
        except (TypeError, ValueError):
            continue
    return matches


def load_existing_results(output_path: Path) -> list[dict[str, Any]]:
    if not output_path.exists():
        return []
    return [record for record in iter_jsonl(output_path) or []]


def selected_pages(pdf_pages: int, args: argparse.Namespace) -> list[int]:
    if args.pages:
        pages = []
        for item in str(args.pages).split(","):
            item = item.strip()
            if not item:
                continue
            page = int(item)
            if page < 1 or page > pdf_pages:
                raise RuntimeError(f"Page out of range: {page}; PDF has {pdf_pages} pages.")
            pages.append(page)
        if not pages:
            raise RuntimeError("--pages did not contain any valid page number.")
        return list(dict.fromkeys(pages))

    start = max(1, int(args.page_start or 1))
    end = min(pdf_pages, int(args.page_end or pdf_pages))
    if not args.include_cover_pages:
        start = max(start, int(args.ignore_first_pages) + 1)
        end = min(end, pdf_pages - int(args.ignore_last_pages))
    if end < start:
        raise RuntimeError(f"Invalid page range: {start}-{end}")
    pages = list(range(start, end + 1))
    if args.max_pages:
        pages = pages[: int(args.max_pages)]
    return pages


def build_summary(
    args: argparse.Namespace,
    pdf_path: Path,
    pdf_url: str,
    pdf_pages: int,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    map_records = [
        record
        for record in records
        if record.get("ai", {}).get("map_plan") is True
    ]
    article_hits: dict[int, dict[str, Any]] = {}
    for record in map_records:
        for article in record.get("articles") or []:
            article_hits[int(article["id"])] = article
    return {
        "created_at": utc_now(),
        "detection_mode": "ai_vision_only_no_text_heuristics",
        "model": args.model,
        "year": args.year,
        "issue": args.issue,
        "pdf_url": pdf_url,
        "pdf_path": relative(pdf_path),
        "pdf_pages": pdf_pages,
        "processed_pages": len(records),
        "map_pages": [
            {
                "page": record["page"],
                "kind": record["ai"]["kind"],
                "confidence": record["ai"]["confidence"],
                "articles": record.get("articles") or [],
            }
            for record in map_records
        ],
        "map_page_count": len(map_records),
        "map_article_count": len(article_hits),
        "map_articles": sorted(article_hits.values(), key=lambda item: int(item["id"])),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--issue", default="1")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--dpi", type=int, default=130)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--pages", help="Comma-separated physical PDF pages, e.g. 1,2,17,59,64,91.")
    parser.add_argument("--page-start", type=int)
    parser.add_argument("--page-end", type=int)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--ignore-first-pages", type=int, default=2)
    parser.add_argument("--ignore-last-pages", type=int, default=4)
    parser.add_argument("--include-cover-pages", action="store_true")
    parser.add_argument("--force", action="store_true", help="Reprocess pages even when output already has them.")
    parser.add_argument("--output-suffix", default="", help="Suffix for smoke/test output names.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.issue = issue_key(args.issue)
    articles = load_issue_articles(args.year, args.issue)
    records = load_issue_fulltext(args.year, args.issue)
    pdf_path, pdf_url = resolve_pdf_path(records, articles)
    pdf_pages = pdf_page_count(pdf_path)

    suffix = f"_{args.output_suffix.strip('_')}" if args.output_suffix else ""
    slug = f"{args.year}_{args.issue}{suffix}"
    output_path = OUTPUT_DIR / f"ai_maps_{slug}.jsonl"
    summary_path = OUTPUT_DIR / f"ai_maps_{slug}_summary.json"
    render_dir = OUTPUT_DIR / "rendered" / slug

    existing = [] if args.force else load_existing_results(output_path)
    by_page = {int(record["page"]): record for record in existing}
    pages = selected_pages(pdf_pages, args)

    for page in pages:
        if page in by_page and not args.force:
            print(f"skip page={page} cached")
            continue
        image_path = render_pdf_page(pdf_path, page, render_dir, args.dpi)
        ai = classify_image(image_path, args.model, args.timeout, args.ollama_url)
        page_articles = [
            {
                "id": article.get("id"),
                "title": article.get("title"),
                "pages": article.get("pages"),
                "pdf_page_start": article.get("pdf_page_start"),
                "pdf_page_end": article.get("pdf_page_end"),
            }
            for article in articles_for_page(page, articles)
        ]
        result = {
            "created_at": utc_now(),
            "detection_mode": "ai_vision_only_no_text_heuristics",
            "model": args.model,
            "year": args.year,
            "issue": args.issue,
            "page": page,
            "image_path": relative(image_path),
            "articles": page_articles,
            "ai": ai,
        }
        by_page[page] = result
        write_jsonl(output_path, list(by_page.values()))
        print(
            "page={page} map_plan={map_plan} confidence={confidence} kind={kind} articles={articles}".format(
                page=page,
                map_plan=ai["map_plan"],
                confidence=ai["confidence"],
                kind=ai["kind"],
                articles=",".join(str(item["id"]) for item in page_articles) or "-",
            )
        )

    final_records = sorted(by_page.values(), key=lambda item: int(item["page"]))
    write_jsonl(output_path, final_records)
    write_json(summary_path, build_summary(args, pdf_path, pdf_url, pdf_pages, final_records))
    print(f"output={relative(output_path)}")
    print(f"summary={relative(summary_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
