#!/usr/bin/env python3
"""Generate public combined and per-journal bibliography exports."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import export_public_sqlite


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
DEFAULT_DATA_EXPORT_DIR = BASE_DIR / "data" / "exports"
DEFAULT_WEB_EXPORT_DIR = BASE_DIR / "web" / "public" / "exports"
DEFAULT_JOURNAL_ID = "spravodaj_sss"

EXPORT_SCOPES = [
    {
        "id": "all",
        "journal_id": None,
        "basename": "bibliografia_vsetko_danko",
        "sqlite": "bibliografia_vsetko.sqlite",
        "title": "Bibliografia speleologických časopisov",
        "group_by_journal": True,
    },
    {
        "id": "spravodaj_sss",
        "journal_id": "spravodaj_sss",
        "basename": "bibliografia_spravodaj_sss_danko",
        "legacy_basename": "spravodaj_sss_danko",
        "sqlite": "bibliografia_spravodaj_sss.sqlite",
        "legacy_sqlite": "spravodaj_sss.sqlite",
        "title": "Bibliografia časopisu Spravodaj SSS",
    },
    {
        "id": "aragonit",
        "journal_id": "aragonit",
        "basename": "bibliografia_aragonit_danko",
        "sqlite": "bibliografia_aragonit.sqlite",
        "title": "Bibliografia časopisu Aragonit",
    },
    {
        "id": "slovensky_kras",
        "journal_id": "slovensky_kras",
        "basename": "bibliografia_slovensky_kras_danko",
        "sqlite": "bibliografia_slovensky_kras.sqlite",
        "title": "Bibliografia časopisu Slovenský kras",
    },
]


def article_journal_id(article: dict[str, Any]) -> str:
    return str(article.get("journal_id") or DEFAULT_JOURNAL_ID)


def scope_articles(articles: list[dict[str, Any]], scope: dict[str, Any]) -> list[dict[str, Any]]:
    journal_id = scope.get("journal_id")
    if not journal_id:
        return list(articles)
    return [article for article in articles if article_journal_id(article) == journal_id]


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def run_danko_export(
    *,
    articles: list[dict[str, Any]],
    scope: dict[str, Any],
    output_dir: Path,
    pdf_engine: str,
) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(articles, handle, ensure_ascii=False)
        temp_path = Path(handle.name)
    try:
        command = [
            sys.executable,
            str(BASE_DIR / "scripts" / "export_lalkovic_format.py"),
            "--articles",
            str(temp_path),
            "--output-dir",
            str(output_dir),
            "--basename",
            str(scope["basename"]),
            "--title",
            str(scope["title"]),
            "--pdf",
            "--pdf-engine",
            pdf_engine,
            "--print-html",
        ]
        if scope.get("group_by_journal"):
            command.append("--group-by-journal")
        subprocess.run(command, check=True)
    finally:
        temp_path.unlink(missing_ok=True)


def write_sqlite_exports(
    *,
    articles: list[dict[str, Any]],
    scope: dict[str, Any],
    data_export_dir: Path,
    web_export_dir: Path,
) -> None:
    data_path = data_export_dir / str(scope["sqlite"])
    export_public_sqlite.export_database(articles, data_path)
    copy_file(data_path, web_export_dir / str(scope["sqlite"]))
    if legacy := scope.get("legacy_sqlite"):
        copy_file(data_path, data_export_dir / str(legacy))
        copy_file(data_path, web_export_dir / str(legacy))


def copy_danko_exports(
    *,
    scope: dict[str, Any],
    data_export_dir: Path,
    web_export_dir: Path,
) -> None:
    basename = str(scope["basename"])
    for extension in ("txt", "md", "html", "pdf"):
        source = data_export_dir / f"{basename}.{extension}"
        copy_file(source, web_export_dir / source.name)
        if legacy_basename := scope.get("legacy_basename"):
            legacy_name = f"{legacy_basename}.{extension}"
            copy_file(source, data_export_dir / legacy_name)
            copy_file(source, web_export_dir / legacy_name)
    print_html_source = data_export_dir / f"{basename}_tlac.html"
    copy_file(print_html_source, web_export_dir / print_html_source.name)
    if legacy_basename := scope.get("legacy_basename"):
        legacy_print_name = f"{legacy_basename}_tlac.html"
        copy_file(print_html_source, data_export_dir / legacy_print_name)
        copy_file(print_html_source, web_export_dir / legacy_print_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--data-export-dir", type=Path, default=DEFAULT_DATA_EXPORT_DIR)
    parser.add_argument("--web-export-dir", type=Path, default=DEFAULT_WEB_EXPORT_DIR)
    parser.add_argument("--pdf-engine", default="wkhtmltopdf")
    parser.add_argument("--scope", action="append", choices=[str(scope["id"]) for scope in EXPORT_SCOPES])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    articles = json.loads(args.articles.read_text(encoding="utf-8"))
    selected_scopes = set(args.scope or [str(scope["id"]) for scope in EXPORT_SCOPES])
    summaries = []
    for scope in EXPORT_SCOPES:
        if str(scope["id"]) not in selected_scopes:
            continue
        selected_articles = scope_articles(articles, scope)
        run_danko_export(
            articles=selected_articles,
            scope=scope,
            output_dir=args.data_export_dir,
            pdf_engine=args.pdf_engine,
        )
        copy_danko_exports(scope=scope, data_export_dir=args.data_export_dir, web_export_dir=args.web_export_dir)
        write_sqlite_exports(
            articles=selected_articles,
            scope=scope,
            data_export_dir=args.data_export_dir,
            web_export_dir=args.web_export_dir,
        )
        summaries.append(
            {
                "scope": scope["id"],
                "articles": len(selected_articles),
                "basename": scope["basename"],
                "sqlite": scope["sqlite"],
            }
        )
    print(json.dumps({"exports": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
