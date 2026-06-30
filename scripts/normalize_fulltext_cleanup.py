#!/usr/bin/env python3
"""Apply safe mechanical cleanup to article fulltext JSONL records."""

import argparse
import datetime as dt
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any

import extract_pdf_fulltext as fulltext


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FULLTEXT_PATH = fulltext.FULLTEXT_PATH
HYPHEN_LINEBREAK_RE = re.compile(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)")
MULTISPACE_RE = re.compile(r"[ \t]{3,}")
TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp_path.replace(path)


def clean_hidden_characters(text: str) -> tuple[str, int]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    allowed = {"\n", "\t"}
    changed = 0
    output: list[str] = []
    for char in text:
        if char in allowed:
            output.append(char)
            continue
        category = unicodedata.category(char)
        if category == "Cc":
            output.append(" ")
            changed += 1
        elif category == "Cf":
            changed += 1
        else:
            output.append(char)
    return "".join(output), changed


def cleanup_text(text: str) -> tuple[str, dict[str, int]]:
    stats = {
        "hidden_chars": 0,
        "hyphen_linebreaks": 0,
        "multispace_runs": 0,
        "trailing_space_lines": 0,
    }
    cleaned, stats["hidden_chars"] = clean_hidden_characters(text)
    cleaned, stats["hyphen_linebreaks"] = HYPHEN_LINEBREAK_RE.subn("", cleaned)
    cleaned, stats["trailing_space_lines"] = TRAILING_SPACE_RE.subn("\n", cleaned)
    cleaned, stats["multispace_runs"] = MULTISPACE_RE.subn(" ", cleaned)
    return cleaned.strip(), stats


def merge_stats(total: dict[str, int], stats: dict[str, int]) -> None:
    for key, value in stats.items():
        total[key] = total.get(key, 0) + int(value)


def update_quality(record: dict[str, Any]) -> None:
    text = record.get("text") or ""
    if "text_quality" in record:
        record["text_quality"] = fulltext.text_quality_metrics(text)


def backup_path(path: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.name}.bak-cleanup-{stamp}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize safe mechanical fulltext cleanup issues.")
    parser.add_argument("--fulltext", type=Path, default=DEFAULT_FULLTEXT_PATH)
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag only reports changes.")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup when applying changes.")
    args = parser.parse_args()

    if not args.fulltext.exists():
        print(f"Missing fulltext file: {args.fulltext}", file=sys.stderr)
        return 1

    records = load_jsonl(args.fulltext)
    changed_records = 0
    total_stats = {
        "hidden_chars": 0,
        "hyphen_linebreaks": 0,
        "multispace_runs": 0,
        "trailing_space_lines": 0,
    }

    for record in records:
        original = record.get("text") or ""
        cleaned, stats = cleanup_text(original)
        if cleaned != original:
            record["text"] = cleaned
            update_quality(record)
            changed_records += 1
            merge_stats(total_stats, stats)

    print(f"records={len(records)} changed_records={changed_records}")
    for key in sorted(total_stats):
        print(f"{key}={total_stats[key]}")

    if not args.apply:
        print("dry_run=1")
        return 0

    if changed_records and not args.no_backup:
        backup = backup_path(args.fulltext)
        shutil.copy2(args.fulltext, backup)
        print(f"backup={backup}")

    write_jsonl(args.fulltext, records)
    print(f"updated={args.fulltext}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
