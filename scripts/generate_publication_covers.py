#!/usr/bin/env python3
"""Generate local WebP cover images for publication PDFs.

The bibliography stores article-level records, but a cover belongs to the
publication PDF. This script renders the first page of each unique PDF into
``web/public/covers/...`` and writes ``cover_url`` back to the article JSON
files so the frontend can use a stable local image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
FRONTEND_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
PDF_CACHE_DIR = BASE_DIR / "data" / "pdf_cache"
COVERS_DIR = BASE_DIR / "web" / "public" / "covers"
MANIFEST_PATH = COVERS_DIR / "manifest.json"

DEFAULT_JOURNAL_ID = "spravodaj_sss"
DEFAULT_JOURNAL_TITLE = "Spravodaj SSS"
COVER_PAGE_OVERRIDES = {
    "http://archiv.smopaj.sk/data/_uploaded/media/public/Slovensky_kras/1_1958.pdf": 2,
}


@dataclass(frozen=True)
class Publication:
    pdf_url: str
    journal_id: str
    journal_title: str
    year: int | None
    issue: str
    volume: str

    @property
    def digest(self) -> str:
        return hashlib.sha1(self.pdf_url.encode("utf-8")).hexdigest()[:10]

    @property
    def cache_pdf_path(self) -> Path:
        return PDF_CACHE_DIR / safe_cache_name(self.pdf_url)

    @property
    def cover_path(self) -> Path:
        journal_dir = COVERS_DIR / self.journal_id
        return journal_dir / f"{safe_cover_stem(self)}.webp"

    @property
    def cover_url(self) -> str:
        return "/" + self.cover_path.relative_to(BASE_DIR / "web" / "public").as_posix()


def strip_url_fragment(url: str) -> str:
    return str(url or "").split("#", 1)[0].strip()


def safe_slug(value: object, fallback: str = "x") -> str:
    text = str(value or "").strip().lower()
    text = (
        text.replace("á", "a")
        .replace("ä", "a")
        .replace("č", "c")
        .replace("ď", "d")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ľ", "l")
        .replace("ĺ", "l")
        .replace("ň", "n")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("ŕ", "r")
        .replace("š", "s")
        .replace("ť", "t")
        .replace("ú", "u")
        .replace("ý", "y")
        .replace("ž", "z")
    )
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def safe_cache_name(url: str) -> str:
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "publication.pdf"
    suffix = Path(filename).suffix.lower() or ".pdf"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    if not stem.lower().endswith(suffix):
        stem += suffix
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{stem}"


def safe_cover_stem(publication: Publication) -> str:
    parts = [
        str(publication.year or "bez-roku"),
        safe_slug(publication.issue, "bez-cisla"),
        publication.digest,
    ]
    return "_".join(parts)


def cover_page_for(publication: Publication) -> int:
    return COVER_PAGE_OVERRIDES.get(publication.pdf_url, 1)


def load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise TypeError(f"{path} neobsahuje JSON zoznam")
    return data


def write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"schema_version": "publication-covers/v1", "covers": {}}
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if "covers" not in manifest or not isinstance(manifest["covers"], dict):
        manifest["covers"] = {}
    manifest.setdefault("schema_version", "publication-covers/v1")
    return manifest


def collect_publications(articles: list[dict]) -> list[Publication]:
    by_url: dict[str, Publication] = {}
    for article in articles:
        pdf_url = strip_url_fragment(article.get("pdf_url", ""))
        if not pdf_url:
            continue
        if pdf_url in by_url:
            continue
        journal_id = str(article.get("journal_id") or DEFAULT_JOURNAL_ID)
        journal_title = str(
            article.get("journal_short_title")
            or article.get("journal_title")
            or DEFAULT_JOURNAL_TITLE
        )
        year = article.get("year")
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None
        by_url[pdf_url] = Publication(
            pdf_url=pdf_url,
            journal_id=journal_id,
            journal_title=journal_title,
            year=year,
            issue=str(article.get("issue") or ""),
            volume=str(article.get("volume") or ""),
        )
    return sorted(
        by_url.values(),
        key=lambda item: (
            item.journal_id,
            item.year or 0,
            natural_key(item.issue),
            item.pdf_url,
        ),
    )


def natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value or "")]


def run(command: list[str], *, quiet: bool = False) -> subprocess.CompletedProcess:
    stdout = subprocess.DEVNULL if quiet else subprocess.PIPE
    stderr = subprocess.PIPE
    return subprocess.run(command, check=False, stdout=stdout, stderr=stderr, text=True)


def ensure_pdf(publication: Publication, timeout: int) -> Path:
    PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = publication.cache_pdf_path
    if cache_path.exists() and cache_path.stat().st_size > 4096:
        return cache_path

    response = requests.get(publication.pdf_url, timeout=timeout, stream=True)
    response.raise_for_status()
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    with tmp_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)
    tmp_path.replace(cache_path)
    return cache_path


def render_cover(publication: Publication, *, width: int, quality: int, timeout: int, force: bool) -> str:
    cover_path = publication.cover_path
    if cover_path.exists() and cover_path.stat().st_size > 1024 and not force:
        return "exists"

    pdf_path = ensure_pdf(publication, timeout)
    cover_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="publication-cover-") as tmpdir:
        tmp_stem = Path(tmpdir) / "page"
        png_path = tmp_stem.with_suffix(".png")
        ppm_result = run(
            [
                "pdftoppm",
                "-f",
                str(cover_page_for(publication)),
                "-l",
                str(cover_page_for(publication)),
                "-singlefile",
                "-scale-to-x",
                str(width),
                "-scale-to-y",
                "-1",
                "-png",
                str(pdf_path),
                str(tmp_stem),
            ],
            quiet=True,
        )
        if ppm_result.returncode != 0 or not png_path.exists():
            raise RuntimeError(f"pdftoppm zlyhal: {ppm_result.stderr.strip()}")

        tmp_webp = cover_path.with_suffix(".webp.tmp")
        cwebp_result = run(
            [
                "cwebp",
                "-quiet",
                "-q",
                str(quality),
                str(png_path),
                "-o",
                str(tmp_webp),
            ],
            quiet=True,
        )
        if cwebp_result.returncode != 0 or not tmp_webp.exists():
            raise RuntimeError(f"cwebp zlyhal: {cwebp_result.stderr.strip()}")
        tmp_webp.replace(cover_path)
    return "created"


def sync_cover_urls(paths: list[Path], cover_urls: dict[str, str]) -> int:
    updated = 0
    for path in paths:
        articles = load_json(path)
        changed = False
        for article in articles:
            pdf_url = strip_url_fragment(article.get("pdf_url", ""))
            cover_url = cover_urls.get(pdf_url)
            if not cover_url:
                continue
            if article.get("cover_url") != cover_url:
                article["cover_url"] = cover_url
                changed = True
                updated += 1
        if changed:
            write_json(path, articles)
    return updated


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=ARTICLES_PATH)
    parser.add_argument("--frontend-articles", type=Path, default=FRONTEND_ARTICLES_PATH)
    parser.add_argument("--journal", action="append", default=[], help="Filter by journal_id. Can be repeated.")
    parser.add_argument("--pdf-url", action="append", default=[], help="Filter by exact source PDF URL. Can be repeated.")
    parser.add_argument("--limit", type=int, default=0, help="Process only N missing covers.")
    parser.add_argument("--max-created", type=int, default=0, help="Render at most N new covers in this run.")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--quality", type=int, default=76)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--force", action="store_true", help="Regenerate existing covers.")
    parser.add_argument("--no-sync", action="store_true", help="Do not write cover_url into article JSON files.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    canonical_articles = load_json(args.articles)
    publications = collect_publications(canonical_articles)
    if args.journal:
        allowed = set(args.journal)
        publications = [item for item in publications if item.journal_id in allowed]
    if args.pdf_url:
        allowed_urls = {strip_url_fragment(url) for url in args.pdf_url}
        publications = [item for item in publications if item.pdf_url in allowed_urls]

    manifest = load_manifest()
    covers: dict[str, dict] = manifest["covers"]
    processed = 0
    created = 0
    existing = 0
    failed: list[dict[str, str]] = []

    for publication in publications:
        if args.limit and processed >= args.limit:
            break
        cover_exists = publication.cover_path.exists() and not args.force
        if args.max_created and created >= args.max_created and not cover_exists:
            break
        if cover_exists:
            status = "exists"
        else:
            try:
                status = render_cover(
                    publication,
                    width=args.width,
                    quality=args.quality,
                    timeout=args.timeout,
                    force=args.force,
                )
            except Exception as exc:  # noqa: BLE001 - report and continue with other PDFs
                failed.append({"pdf_url": publication.pdf_url, "error": str(exc)})
                print(f"FAIL {publication.pdf_url}: {exc}", flush=True)
                processed += 1
                continue

        if status == "created":
            created += 1
            print(f"CREATED {publication.cover_url}", flush=True)
        else:
            existing += 1

        covers[publication.pdf_url] = {
            "cover_url": publication.cover_url,
            "journal_id": publication.journal_id,
            "journal_title": publication.journal_title,
            "year": publication.year,
            "issue": publication.issue,
            "volume": publication.volume,
            "cover_page": cover_page_for(publication),
            "source_pdf_url": publication.pdf_url,
        }
        processed += 1

    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    manifest["covers"] = dict(sorted(covers.items()))
    write_json(MANIFEST_PATH, manifest)

    synced = 0
    if not args.no_sync:
        cover_urls = {pdf_url: entry["cover_url"] for pdf_url, entry in covers.items()}
        synced = sync_cover_urls([args.articles, args.frontend_articles], cover_urls)

    print(
        json.dumps(
            {
                "publications_total": len(publications),
                "processed": processed,
                "created": created,
                "existing": existing,
                "failed": len(failed),
                "article_cover_url_updates": synced,
                "manifest": str(MANIFEST_PATH.relative_to(BASE_DIR)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if failed:
        report_path = BASE_DIR / "data" / "publication_cover_failures.json"
        write_json(report_path, failed)
        print(f"Failure report: {report_path.relative_to(BASE_DIR)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
