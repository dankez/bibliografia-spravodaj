#!/usr/bin/env python3
"""Reconcile article fulltext JSONL against canonical article metadata."""

import argparse
import collections
import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import extract_pdf_fulltext as fulltext


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = BASE_DIR / "reports" / "fulltext_reconcile_report.json"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            record["_line"] = line_number
            records.append(record)
    return records


def load_articles(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"Expected article list in {path}")
    return payload


def clean_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def create_backup(path: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.bak-reconcile-{stamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(clean_record(record), ensure_ascii=False) + "\n")
    temp_path.replace(path)


def text_metrics(record: dict[str, Any]) -> dict[str, Any]:
    text = record.get("text") or ""
    metrics = record.get("text_quality")
    if isinstance(metrics, dict):
        return metrics
    return fulltext.text_quality_metrics(text)


def record_rank(record: dict[str, Any]) -> tuple[int, int, int, int, int, int, int]:
    text = record.get("text") or ""
    has_text = 1 if text.strip() else 0
    status = record.get("status") or ""
    status_text_rank = 0
    if has_text and status == "ok":
        status_text_rank = 5
    elif has_text:
        status_text_rank = 3
    elif status == "ok":
        status_text_rank = 2
    elif status == "empty_text":
        status_text_rank = 1

    metrics = text_metrics(record)
    bad_tokens = int(metrics.get("bad_diacritic_token_count") or 0)
    words = int(metrics.get("words") or 0)
    source_bonus = 1 if record.get("text_source") == "tesseract_ocr" else 0
    line = int(record.get("_line") or 0)
    return (
        status_text_rank,
        source_bonus,
        -bad_tokens,
        words,
        len(text),
        int(record.get("text_chars") or 0),
        -line,
    )


def select_best(records: list[dict[str, Any]]) -> dict[str, Any]:
    return max(records, key=record_rank)


def group_by_id(records: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        article_id = record.get("id")
        if article_id is None:
            continue
        grouped[int(article_id)].append(record)
    return dict(grouped)


def compact_choice(record: dict[str, Any]) -> dict[str, Any]:
    text = record.get("text") or ""
    metrics = text_metrics(record)
    return {
        "line": record.get("_line"),
        "id": record.get("id"),
        "status": record.get("status"),
        "text_source": record.get("text_source") or "pdftotext",
        "text_chars": len(text),
        "words": int(metrics.get("words") or 0),
        "bad_diacritic_token_count": int(metrics.get("bad_diacritic_token_count") or 0),
        "year": record.get("year"),
        "issue": record.get("issue"),
        "pages": record.get("pages"),
        "title": record.get("title"),
        "rank": list(record_rank(record)),
    }


def reconcile(records: list[dict[str, Any]], articles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    article_ids = [int(article["id"]) for article in articles if article.get("id") is not None]
    article_id_set = set(article_ids)
    grouped = group_by_id(records)
    selected_by_id: dict[int, dict[str, Any]] = {}
    duplicate_details: list[dict[str, Any]] = []

    for article_id, group in grouped.items():
        selected = select_best(group)
        selected_by_id[article_id] = selected
        if len(group) > 1:
            duplicate_details.append(
                {
                    "id": article_id,
                    "selected": compact_choice(selected),
                    "dropped": [
                        compact_choice(record)
                        for record in group
                        if record is not selected
                    ],
                }
            )

    output_records: list[dict[str, Any]] = [
        selected_by_id[article_id]
        for article_id in article_ids
        if article_id in selected_by_id
    ]
    orphan_ids = sorted(set(grouped) - article_id_set)
    output_records.extend(selected_by_id[article_id] for article_id in orphan_ids)

    input_ids = set(grouped)
    missing_ids = sorted(article_id_set - input_ids)
    status_counts = collections.Counter((record.get("status") or "") for record in output_records)
    source_counts = collections.Counter((record.get("text_source") or "pdftotext") for record in output_records)
    selected_from_later_line = sum(
        1
        for detail in duplicate_details
        if detail["selected"]["line"] != min(
            [detail["selected"]["line"]] + [item["line"] for item in detail["dropped"]]
        )
    )

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "summary": {
            "input_records": len(records),
            "input_unique_ids": len(input_ids),
            "article_records": len(articles),
            "article_unique_ids": len(article_id_set),
            "output_records": len(output_records),
            "removed_records": len(records) - len(output_records),
            "duplicate_article_ids": len(duplicate_details),
            "duplicate_input_records": sum(len(group) for group in grouped.values() if len(group) > 1),
            "selected_from_later_line": selected_from_later_line,
            "missing_fulltext_for_articles": len(missing_ids),
            "fulltext_without_article": len(orphan_ids),
            "output_status_counts": dict(status_counts),
            "output_text_source_counts": dict(source_counts),
        },
        "duplicate_details": sorted(duplicate_details, key=lambda item: item["id"]),
        "missing_article_ids": missing_ids,
        "fulltext_without_article_ids": orphan_ids,
    }
    return output_records, report


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dedupe and reconcile article_fulltext.jsonl by article ID.")
    parser.add_argument("--fulltext", type=Path, default=fulltext.FULLTEXT_PATH)
    parser.add_argument("--articles", type=Path, default=fulltext.ARTICLES_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--output", type=Path, default=None, help="Write reconciled JSONL here instead of in-place.")
    parser.add_argument("--dry-run", action="store_true", help="Only write report and print summary.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a backup before in-place write.")
    args = parser.parse_args()

    if not args.fulltext.exists():
        print(f"Missing fulltext file: {args.fulltext}", file=sys.stderr)
        return 1
    if not args.articles.exists():
        print(f"Missing articles file: {args.articles}", file=sys.stderr)
        return 1

    records = load_jsonl(args.fulltext)
    articles = load_articles(args.articles)
    output_records, report = reconcile(records, articles)
    write_report(args.report, report)

    summary = report["summary"]
    print(
        "input_records={input_records} output_records={output_records} removed_records={removed_records}".format(
            **summary
        )
    )
    print(
        "duplicate_article_ids={duplicate_article_ids} missing_fulltext_for_articles={missing_fulltext_for_articles} "
        "fulltext_without_article={fulltext_without_article}".format(**summary)
    )
    print(f"report={args.report}")

    if args.dry_run:
        return 0

    output_path = args.output or args.fulltext
    backup_path = None
    if output_path == args.fulltext and not args.no_backup:
        backup_path = create_backup(args.fulltext)
        print(f"backup={backup_path}")
    write_jsonl(output_path, output_records)
    print(f"output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
