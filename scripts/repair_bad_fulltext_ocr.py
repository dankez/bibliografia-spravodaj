#!/usr/bin/env python3
"""Repair article fulltext records whose PDF text layer has broken diacritics."""

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import extract_pdf_fulltext as fulltext


def int_or_none(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def load_records(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def create_backup(path: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def write_records(path: Path, records: list[dict]) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp_path.replace(path)


def selected_ids(value: str) -> set[int] | None:
    if not value:
        return None
    ids: set[int] = set()
    for chunk in value.split(","):
        chunk = chunk.strip()
        if chunk:
            ids.add(int(chunk))
    return ids


def repair_candidate(
    record: dict,
    pdf_text_layer: dict,
    reason: str,
    args: argparse.Namespace,
) -> tuple[dict, str]:
    pdf_cache = record.get("pdf_cache") or ""
    pdf_path = fulltext.BASE_DIR / pdf_cache
    physical_start = int_or_none(record.get("pdf_page_start"))
    physical_end = int_or_none(record.get("pdf_page_end")) or physical_start
    if physical_start is None or physical_end is None:
        return record, "missing_pdf_page_range"
    if not pdf_path.exists():
        return record, "missing_pdf_cache"

    try:
        page_texts: list[str] = []
        ocr_meta = None
        for page in range(physical_start, physical_end + 1):
            print(f"     OCR page {page}/{physical_end}", flush=True)
            page_text, page_meta = fulltext.tesseract_pdf_range(
                pdf_path,
                page,
                page,
                args.ocr_languages,
                args.ocr_dpi,
                args.ocr_timeout,
                args.ocr_cpu,
            )
            page_texts.append(page_text)
            ocr_meta = page_meta
        ocr_text = "\n\n".join(text for text in page_texts if text)
        if ocr_meta is None:
            ocr_meta = {
                "engine": "tesseract",
                "languages": args.ocr_languages,
                "missing_languages": [],
                "dpi": args.ocr_dpi,
                "timeout_seconds_per_page": args.ocr_timeout,
                "cpu": args.ocr_cpu,
                "thread_limit": 1,
            }
        ocr_meta["pages"] = len(page_texts)
    except Exception as exc:
        updated = dict(record)
        updated["pdf_text_layer"] = pdf_text_layer
        updated["ocr"] = {
            "engine": "tesseract",
            "trigger": reason,
            "accepted": False,
            "error": str(exc),
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        return updated, "ocr_error"

    use_ocr, decision = fulltext.choose_ocr_text(record.get("text") or "", ocr_text, "bad-text")
    ocr_quality = fulltext.text_quality_metrics(ocr_text)
    ocr_meta.update(
        {
            "trigger": reason,
            "decision": decision,
            "accepted": use_ocr,
            "quality": ocr_quality,
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )

    updated = dict(record)
    updated["pdf_text_layer"] = pdf_text_layer
    updated["ocr"] = ocr_meta
    if use_ocr:
        updated["text"] = ocr_text
        updated["text_chars"] = len(ocr_text)
        updated["text_source"] = "tesseract_ocr"
        updated["text_quality"] = ocr_quality
        updated["status"] = "ok" if ocr_text.strip() else "empty_text"
        updated["extracted_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        return updated, "accepted"

    updated.setdefault("text_source", "pdftotext")
    updated["text_quality"] = fulltext.text_quality_metrics(record.get("text") or "")
    return updated, decision


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair bad fulltext records with safe one-CPU Tesseract OCR.")
    parser.add_argument("--fulltext", type=Path, default=fulltext.FULLTEXT_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Only report candidates; do not OCR or write.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a .bak copy before in-place write.")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N candidates.")
    parser.add_argument("--ids", default="", help="Comma-separated article IDs to consider.")
    parser.add_argument("--min-bad-tokens", type=int, default=4)
    parser.add_argument("--min-chars", type=int, default=600)
    parser.add_argument("--ocr-languages", default="slk+ces")
    parser.add_argument("--ocr-dpi", type=int, default=300)
    parser.add_argument("--ocr-timeout", type=int, default=120)
    parser.add_argument("--ocr-cpu", type=int, default=0)
    parser.add_argument("--checkpoint-every", type=int, default=1, help="Write JSONL after every N repaired candidates.")
    args = parser.parse_args()

    if not args.fulltext.exists():
        print(f"Missing fulltext file: {args.fulltext}", file=sys.stderr)
        return 1

    if not args.dry_run:
        for binary in ("pdffonts", "pdftoppm", "tesseract"):
            if not fulltext.shutil_which(binary):
                print(f"Error: {binary} is required.", file=sys.stderr)
                return 1

    records = load_records(args.fulltext)
    wanted_ids = selected_ids(args.ids)
    font_cache: dict[str, dict] = {}
    candidates: list[tuple[int, dict, dict, str, dict]] = []

    for index, record in enumerate(records):
        article_id = record.get("id")
        if wanted_ids is not None and article_id not in wanted_ids:
            continue
        text = record.get("text") or ""
        metrics = fulltext.text_quality_metrics(text)
        bad_count = int(metrics.get("bad_diacritic_token_count") or 0)
        if not text.strip() or len(text) < args.min_chars:
            continue
        if bad_count < args.min_bad_tokens:
            continue
        pdf_cache = record.get("pdf_cache") or ""
        font_summary = font_cache.get(pdf_cache)
        if font_summary is None:
            pdf_path = fulltext.BASE_DIR / pdf_cache
            font_summary = fulltext.pdffonts_summary(pdf_path) if pdf_path.exists() else {"status": "missing_pdf"}
            font_cache[pdf_cache] = font_summary
        should_ocr, reason = fulltext.should_reocr_text_layer(
            text,
            metrics,
            font_summary,
            args.min_bad_tokens,
            args.min_chars,
        )
        if not should_ocr and bad_count >= args.min_bad_tokens:
            should_ocr = True
            reason = "bad_tokens"
        if not should_ocr:
            continue
        candidates.append((index, record, font_summary, reason, metrics))
        if args.limit is not None and len(candidates) >= args.limit:
            break

    print(f"records={len(records)} candidates={len(candidates)}")
    for _, record, _, reason, metrics in candidates[:20]:
        print(
            f"candidate id={record.get('id')} pages={record.get('pdf_page_start')}-{record.get('pdf_page_end')} "
            f"bad={metrics['bad_diacritic_token_count']} reason={reason} title={record.get('title')}"
        )
    if args.dry_run:
        return 0

    backup_path = None
    if not args.no_backup:
        backup_path = create_backup(args.fulltext)
        print(f"Backup: {backup_path}", flush=True)

    stats: dict[str, int] = {}
    last_checkpoint = 0
    for position, (index, record, font_summary, reason, metrics) in enumerate(candidates, start=1):
        print(
            f"[{position}/{len(candidates)}] id={record.get('id')} "
            f"pages={record.get('pdf_page_start')}-{record.get('pdf_page_end')} "
            f"bad={metrics['bad_diacritic_token_count']}",
            flush=True,
        )
        updated, outcome = repair_candidate(record, font_summary, reason, args)
        records[index] = updated
        stats[outcome] = stats.get(outcome, 0) + 1
        print(f"  -> {outcome}", flush=True)
        if args.checkpoint_every > 0 and position % args.checkpoint_every == 0:
            write_records(args.fulltext, records)
            last_checkpoint = position
            print(f"  checkpoint written at {position}/{len(candidates)}", flush=True)

    if last_checkpoint != len(candidates):
        write_records(args.fulltext, records)
    print(f"Done. stats={stats}, output={args.fulltext}")
    if backup_path:
        print(f"Backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
