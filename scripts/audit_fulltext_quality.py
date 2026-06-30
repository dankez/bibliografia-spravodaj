#!/usr/bin/env python3
"""Audit article fulltext quality and write actionable reports."""

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import extract_pdf_fulltext as fulltext


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports"
SEVERITY_SCORE = {"high": 100, "medium": 50, "low": 10}
ISSUE_SCORE = {
    "empty_text": 300,
    "very_short_text": 250,
    "low_text_density": 100,
    "replacement_characters": 220,
    "control_characters": 180,
    "private_use_characters": 160,
    "other_hidden_characters": 160,
    "residual_bad_diacritic_tokens": 120,
    "cleanup_format_characters": 30,
    "cleanup_hyphen_linebreaks": 20,
    "cleanup_multispace_layout": 10,
}
IGNORABLE_OUTER_MATTER_ISSUES = {
    "empty_text",
    "very_short_text",
    "low_text_density",
    "replacement_characters",
    "control_characters",
    "private_use_characters",
    "other_hidden_characters",
    "residual_bad_diacritic_tokens",
    "cleanup_format_characters",
    "cleanup_hyphen_linebreaks",
    "cleanup_multispace_layout",
}
HYPHEN_LINEBREAK_RE = re.compile(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)")
MULTISPACE_RE = re.compile(r"[ \t]{3,}")
WHITESPACE_RE = re.compile(r"\s+")


def int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def page_span(record: dict[str, Any]) -> int:
    start = int_or_none(record.get("pdf_page_start")) or int_or_none(record.get("page_start"))
    end = int_or_none(record.get("pdf_page_end")) or int_or_none(record.get("page_end")) or start
    if start is None or end is None or end < start:
        return 1
    return max(1, end - start + 1)


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                record = json.loads(line)
                record["_line"] = line_number
                records.append(record)
    return records


def hidden_char_counts(text: str) -> dict[str, int]:
    allowed = {"\n", "\r", "\t", "\f"}
    counts = {"control": 0, "format": 0, "private_use": 0, "other": 0}
    for char in text:
        if char in allowed:
            continue
        category = unicodedata.category(char)
        if category == "Cc":
            counts["control"] += 1
        elif category == "Cf":
            counts["format"] += 1
        elif category == "Co":
            counts["private_use"] += 1
        elif category.startswith("C"):
            counts["other"] += 1
    return counts


def text_signals(record: dict[str, Any]) -> dict[str, Any]:
    text = record.get("text") or ""
    pages = page_span(record)
    metrics = dict(record.get("text_quality") or fulltext.text_quality_metrics(text))
    chars = len(text)
    words = int(metrics.get("words") or 0)
    hidden_chars = hidden_char_counts(text)
    return {
        "chars": chars,
        "words": words,
        "pages": pages,
        "chars_per_page": chars / pages if pages else chars,
        "words_per_page": words / pages if pages else words,
        "diacritics": int(metrics.get("diacritics") or 0),
        "bad_diacritic_token_count": int(metrics.get("bad_diacritic_token_count") or 0),
        "bad_diacritic_token_examples": metrics.get("bad_diacritic_token_examples") or [],
        "hyphen_linebreaks": len(HYPHEN_LINEBREAK_RE.findall(text)),
        "multispace_runs": len(MULTISPACE_RE.findall(text)),
        "replacement_chars": text.count("\ufffd"),
        "control_chars": hidden_chars["control"],
        "format_chars": hidden_chars["format"],
        "private_use_chars": hidden_chars["private_use"],
        "other_hidden_chars": hidden_chars["other"],
    }


def add_issue(
    issues: list[dict[str, Any]],
    code: str,
    severity: str,
    detail: str,
    value: Any = None,
) -> None:
    issue = {"code": code, "severity": severity, "detail": detail}
    if value is not None:
        issue["value"] = value
    issues.append(issue)


def classify_record(record: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    signals = text_signals(record)
    text = record.get("text") or ""
    status = record.get("status") or ""
    issues: list[dict[str, Any]] = []

    if not text.strip():
        add_issue(issues, "empty_text", "high", f"status={status or 'missing'}")
    elif status and status != "ok":
        add_issue(issues, "non_ok_status", "high", f"status={status}")

    if text.strip() and (signals["chars"] < args.min_chars or signals["words"] < args.min_words):
        add_issue(
            issues,
            "very_short_text",
            "high",
            f"{signals['chars']} chars, {signals['words']} words",
            {"chars": signals["chars"], "words": signals["words"]},
        )

    if (
        text.strip()
        and signals["chars_per_page"] < args.min_chars_per_page
        and signals["words_per_page"] < args.min_words_per_page
    ):
        add_issue(
            issues,
            "low_text_density",
            "medium",
            f"{signals['chars_per_page']:.1f} chars/page, {signals['words_per_page']:.1f} words/page",
            {
                "chars_per_page": round(signals["chars_per_page"], 2),
                "words_per_page": round(signals["words_per_page"], 2),
            },
        )

    bad_count = signals["bad_diacritic_token_count"]
    if bad_count >= args.bad_token_threshold:
        add_issue(
            issues,
            "residual_bad_diacritic_tokens",
            "medium",
            ", ".join(signals["bad_diacritic_token_examples"][:8]),
            {"count": bad_count, "examples": signals["bad_diacritic_token_examples"][:8]},
        )

    if signals["replacement_chars"]:
        add_issue(
            issues,
            "replacement_characters",
            "high" if signals["replacement_chars"] >= 5 else "medium",
            f"{signals['replacement_chars']} replacement chars",
            signals["replacement_chars"],
        )

    if signals["control_chars"]:
        add_issue(
            issues,
            "control_characters",
            "medium",
            f"{signals['control_chars']} unexpected control chars",
            signals["control_chars"],
        )

    if signals["private_use_chars"]:
        add_issue(
            issues,
            "private_use_characters",
            "medium",
            f"{signals['private_use_chars']} private-use chars",
            signals["private_use_chars"],
        )

    if signals["other_hidden_chars"]:
        add_issue(
            issues,
            "other_hidden_characters",
            "medium",
            f"{signals['other_hidden_chars']} hidden chars",
            signals["other_hidden_chars"],
        )

    if signals["format_chars"] >= args.format_char_threshold:
        add_issue(
            issues,
            "cleanup_format_characters",
            "low",
            f"{signals['format_chars']} format chars",
            signals["format_chars"],
        )

    if signals["hyphen_linebreaks"] >= args.hyphen_linebreak_threshold:
        add_issue(
            issues,
            "cleanup_hyphen_linebreaks",
            "low",
            f"{signals['hyphen_linebreaks']} hyphenated line breaks",
            signals["hyphen_linebreaks"],
        )

    if signals["multispace_runs"] >= args.multispace_threshold:
        add_issue(
            issues,
            "cleanup_multispace_layout",
            "low",
            f"{signals['multispace_runs']} wide spacing runs",
            signals["multispace_runs"],
        )

    return signals, issues


def normalized_text_hash(text: str, min_chars: int) -> str | None:
    normalized = WHITESPACE_RE.sub(" ", text).strip().casefold()
    if len(normalized) < min_chars:
        return None
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def duplicate_groups(records: list[dict[str, Any]], min_chars: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    lengths: dict[str, int] = {}
    for record in records:
        text = record.get("text") or ""
        digest = normalized_text_hash(text, min_chars)
        if not digest:
            continue
        groups[digest].append(record)
        lengths[digest] = len(WHITESPACE_RE.sub(" ", text).strip())

    duplicates: list[dict[str, Any]] = []
    for digest, group in groups.items():
        if len(group) < 2:
            continue
        pdf_pages = {
            (
                item.get("pdf_cache") or "",
                item.get("pdf_page_start"),
                item.get("pdf_page_end"),
            )
            for item in group
        }
        duplicates.append(
            {
                "hash": digest,
                "records": [
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "year": item.get("year"),
                        "issue": item.get("issue"),
                        "pages": item.get("pages"),
                        "pdf_page_start": item.get("pdf_page_start"),
                        "pdf_page_end": item.get("pdf_page_end"),
                    }
                    for item in group
                ],
                "record_count": len(group),
                "normalized_chars": lengths[digest],
                "same_pdf_pages": len(pdf_pages) == 1,
            }
        )
    duplicates.sort(key=lambda item: (-item["record_count"], -item["normalized_chars"]))
    return duplicates


def issue_score(issues: list[dict[str, Any]]) -> int:
    return sum(ISSUE_SCORE.get(issue["code"], SEVERITY_SCORE.get(issue["severity"], 0)) for issue in issues)


def is_outer_matter_range(record: dict[str, Any], pdf_pages: int | None) -> bool:
    start = int_or_none(record.get("pdf_page_start"))
    end = int_or_none(record.get("pdf_page_end")) or start
    if start is None or end is None:
        return False
    if end < start:
        end = start
    outer_pages = {1, 2}
    if pdf_pages is not None:
        outer_pages.update({max(1, pdf_pages - 1), max(1, pdf_pages)})
    return all(page in outer_pages for page in range(start, end + 1))


def ignore_outer_matter_issues(
    record: dict[str, Any],
    issues: list[dict[str, Any]],
    pdf_pages: int | None,
) -> tuple[list[dict[str, Any]], str | None]:
    if not issues or not is_outer_matter_range(record, pdf_pages):
        return issues, None
    if all(issue["code"] in IGNORABLE_OUTER_MATTER_ISSUES for issue in issues):
        return [], "outer_matter_page"
    return issues, None


def cached_pdf_page_count(record: dict[str, Any], cache: dict[str, int | None]) -> int | None:
    pdf_cache = record.get("pdf_cache") or ""
    if not pdf_cache:
        return None
    if pdf_cache not in cache:
        pdf_path = fulltext.BASE_DIR / pdf_cache
        if not pdf_path.exists():
            cache[pdf_cache] = None
        else:
            try:
                cache[pdf_cache] = fulltext.pdf_page_count(pdf_path)
            except Exception:
                cache[pdf_cache] = None
    return cache[pdf_cache]


def pdf_page_url(pdf_url: str, page: int) -> str:
    base = pdf_url.split("#", 1)[0]
    return f"{base}#page={page}"


def candidate_pdf_pages(record: dict[str, Any], pdf_pages: int | None, max_links: int = 3) -> list[int]:
    start = int_or_none(record.get("pdf_page_start"))
    end = int_or_none(record.get("pdf_page_end")) or start
    wanted: list[int] = []

    if start is not None:
        if end is None or end < start:
            end = start
        if start == end:
            wanted.extend([start - 1, start, start + 1, start + 2])
        else:
            wanted.extend([start, start + max(0, end - start) // 2, end])
    elif record.get("status") == "page_out_of_range" and pdf_pages:
        wanted.extend([max(1, pdf_pages - 2), max(1, pdf_pages - 1), pdf_pages])
    elif pdf_pages:
        wanted.extend([1, max(1, (pdf_pages + 1) // 2), pdf_pages])

    pages: list[int] = []
    for page in wanted:
        if page < 1:
            continue
        if pdf_pages is not None and page > pdf_pages:
            continue
        if page not in pages:
            pages.append(page)
        if len(pages) >= max_links:
            break

    if len(pages) < max_links and pages:
        anchor = pages[-1]
        for delta in range(1, max_links + 3):
            for page in (anchor + delta, anchor - delta):
                if page < 1:
                    continue
                if pdf_pages is not None and page > pdf_pages:
                    continue
                if page not in pages:
                    pages.append(page)
                if len(pages) >= max_links:
                    return pages
    return pages


def pdf_page_links(record: dict[str, Any], pdf_pages: int | None, max_links: int = 3) -> list[dict[str, Any]]:
    pdf_url = record.get("pdf_url") or ""
    if not pdf_url:
        return []
    return [
        {"page": page, "url": pdf_page_url(pdf_url, page)}
        for page in candidate_pdf_pages(record, pdf_pages, max_links=max_links)
    ]


def compact_record(
    record: dict[str, Any],
    signals: dict[str, Any],
    issues: list[dict[str, Any]],
    pdf_pages: int | None = None,
    ignored_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "line": record.get("_line"),
        "title": record.get("title"),
        "year": record.get("year"),
        "issue": record.get("issue"),
        "pages": record.get("pages"),
        "pdf_url": record.get("pdf_url"),
        "pdf_pages": pdf_pages,
        "pdf_page_links": pdf_page_links(record, pdf_pages),
        "pdf_page_start": record.get("pdf_page_start"),
        "pdf_page_end": record.get("pdf_page_end"),
        "status": record.get("status"),
        "text_source": record.get("text_source") or "pdftotext",
        "text_chars": signals["chars"],
        "words": signals["words"],
        "chars_per_page": round(signals["chars_per_page"], 2),
        "words_per_page": round(signals["words_per_page"], 2),
        "bad_diacritic_token_count": signals["bad_diacritic_token_count"],
        "bad_diacritic_token_examples": signals["bad_diacritic_token_examples"],
        "hyphen_linebreaks": signals["hyphen_linebreaks"],
        "multispace_runs": signals["multispace_runs"],
        "replacement_chars": signals["replacement_chars"],
        "control_chars": signals["control_chars"],
        "format_chars": signals["format_chars"],
        "private_use_chars": signals["private_use_chars"],
        "other_hidden_chars": signals["other_hidden_chars"],
        "ignored_reason": ignored_reason,
        "issue_score": issue_score(issues),
        "issues": issues,
    }


def make_summary(
    records: list[dict[str, Any]],
    audited: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = collections.Counter(str(record.get("status") or "") for record in records)
    text_source_counts = collections.Counter(str(record.get("text_source") or "pdftotext") for record in records)
    id_counts = collections.Counter(record.get("id") for record in records if record.get("id") is not None)
    duplicate_article_ids = [count for count in id_counts.values() if count > 1]
    issue_counts = collections.Counter()
    severity_counts = collections.Counter()
    bad_token_counts = collections.Counter()
    for item in audited:
        bad = int(item["bad_diacritic_token_count"])
        for threshold in (1, 2, 3, 4):
            if bad >= threshold:
                bad_token_counts[f">={threshold}"] += 1
        for issue in item["issues"]:
            issue_counts[issue["code"]] += 1
            severity_counts[issue["severity"]] += 1

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "records": len(records),
        "records_with_text": sum(1 for record in records if (record.get("text") or "").strip()),
        "records_without_text": sum(1 for record in records if not (record.get("text") or "").strip()),
        "records_with_issues": sum(1 for item in audited if item["issues"]),
        "ignored_outer_matter_records": sum(
            1 for item in audited if item.get("ignored_reason") == "outer_matter_page"
        ),
        "status_counts": dict(status_counts),
        "text_source_counts": dict(text_source_counts),
        "issue_counts": dict(issue_counts),
        "severity_counts": dict(severity_counts),
        "bad_token_records": dict(bad_token_counts),
        "duplicate_groups": len(duplicates),
        "duplicate_records": sum(group["record_count"] for group in duplicates),
        "duplicate_groups_same_pdf_pages": sum(1 for group in duplicates if group["same_pdf_pages"]),
        "duplicate_article_ids": len(duplicate_article_ids),
        "duplicate_article_id_records": sum(duplicate_article_ids),
    }


def markdown_table(rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    lines = [
        "| " + " | ".join(str(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def markdown_pdf_links(item: dict[str, Any]) -> str:
    return " ".join(
        f"[p{link['page']}]({link['url']})"
        for link in item.get("pdf_page_links", [])
    )


def write_markdown_report(path: Path, summary: dict[str, Any], audited: list[dict[str, Any]], duplicates: list[dict[str, Any]], max_items: int) -> None:
    issue_rows = [["code", "count"]]
    for code, count in sorted(summary["issue_counts"].items(), key=lambda item: (-item[1], item[0])):
        issue_rows.append([code, count])

    top_issues = [item for item in audited if item["issues"]]
    top_issues.sort(key=lambda item: (-item["issue_score"], item["id"] or 0))
    top_rows = [["line", "id", "year", "pages", "pdf links", "status", "score", "issues", "title"]]
    for item in top_issues[:max_items]:
        top_rows.append(
            [
                item["line"],
                item["id"],
                item["year"],
                item["pages"],
                markdown_pdf_links(item),
                item["status"],
                item["issue_score"],
                ", ".join(issue["code"] for issue in item["issues"]),
                item["title"],
            ]
        )

    empty_rows = [["line", "id", "year", "pages", "pdf links", "status", "title"]]
    for item in [row for row in audited if row["text_chars"] == 0 and not row.get("ignored_reason")]:
        empty_rows.append(
            [
                item["line"],
                item["id"],
                item["year"],
                item["pages"],
                markdown_pdf_links(item),
                item["status"],
                item["title"],
            ]
        )

    ignored_rows = [["line", "id", "year", "pages", "pdf links", "status", "reason", "title"]]
    for item in [row for row in audited if row.get("ignored_reason")]:
        ignored_rows.append(
            [
                item["line"],
                item["id"],
                item["year"],
                item["pages"],
                markdown_pdf_links(item),
                item["status"],
                item["ignored_reason"],
                item["title"],
            ]
        )

    duplicate_rows = [["records", "same pages", "chars", "ids", "titles"]]
    for group in duplicates[:50]:
        ids = ", ".join(str(item["id"]) for item in group["records"][:10])
        titles = " / ".join(str(item["title"]) for item in group["records"][:3])
        duplicate_rows.append(
            [
                group["record_count"],
                "yes" if group["same_pdf_pages"] else "no",
                group["normalized_chars"],
                ids,
                titles,
            ]
        )

    lines = [
        "# Fulltext quality audit",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- records: {summary['records']}",
        f"- records with text: {summary['records_with_text']}",
        f"- records without text: {summary['records_without_text']}",
        f"- records with issues: {summary['records_with_issues']}",
        f"- ignored outer-matter records: {summary['ignored_outer_matter_records']}",
        f"- duplicate groups: {summary['duplicate_groups']} ({summary['duplicate_records']} records)",
        f"- duplicate groups on the same PDF page range: {summary['duplicate_groups_same_pdf_pages']}",
        f"- duplicate article IDs: {summary['duplicate_article_ids']} ({summary['duplicate_article_id_records']} records)",
        f"- status counts: `{json.dumps(summary['status_counts'], ensure_ascii=False)}`",
        f"- text source counts: `{json.dumps(summary['text_source_counts'], ensure_ascii=False)}`",
        f"- bad token records: `{json.dumps(summary['bad_token_records'], ensure_ascii=False)}`",
        "",
        "## Issue Counts",
        "",
        markdown_table(issue_rows),
        "",
        "## Highest Priority Records",
        "",
        markdown_table(top_rows),
        "",
        "## Records Without Text",
        "",
        markdown_table(empty_rows),
        "",
        "## Ignored Outer Matter",
        "",
        markdown_table(ignored_rows),
        "",
        "## Duplicate Fulltext Groups",
        "",
        markdown_table(duplicate_rows),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json_report(path: Path, summary: dict[str, Any], audited: list[dict[str, Any]], duplicates: list[dict[str, Any]]) -> None:
    payload = {
        "summary": summary,
        "records": audited,
        "duplicate_groups": duplicates,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit article fulltext quality without mutating source data.")
    parser.add_argument("--fulltext", type=Path, default=fulltext.FULLTEXT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--prefix", default="fulltext_quality_audit")
    parser.add_argument("--max-items", type=int, default=200)
    parser.add_argument("--min-chars", type=int, default=300)
    parser.add_argument("--min-words", type=int, default=30)
    parser.add_argument("--min-chars-per-page", type=int, default=600)
    parser.add_argument("--min-words-per-page", type=int, default=80)
    parser.add_argument("--bad-token-threshold", type=int, default=2)
    parser.add_argument("--hyphen-linebreak-threshold", type=int, default=100)
    parser.add_argument("--multispace-threshold", type=int, default=500)
    parser.add_argument("--format-char-threshold", type=int, default=25)
    parser.add_argument("--duplicate-min-chars", type=int, default=500)
    args = parser.parse_args()

    if not args.fulltext.exists():
        print(f"Missing fulltext file: {args.fulltext}", file=sys.stderr)
        return 1

    records = load_records(args.fulltext)
    audited: list[dict[str, Any]] = []
    pdf_page_count_cache: dict[str, int | None] = {}
    for record in records:
        signals, issues = classify_record(record, args)
        pdf_pages = cached_pdf_page_count(record, pdf_page_count_cache) if issues else None
        issues, ignored_reason = ignore_outer_matter_issues(record, issues, pdf_pages)
        audited.append(compact_record(record, signals, issues, pdf_pages, ignored_reason))

    duplicates = duplicate_groups(records, args.duplicate_min_chars)
    summary = make_summary(records, audited, duplicates)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"{args.prefix}.json"
    markdown_path = args.output_dir / f"{args.prefix}.md"
    write_json_report(json_path, summary, audited, duplicates)
    write_markdown_report(markdown_path, summary, audited, duplicates, args.max_items)

    print(f"records={summary['records']} records_with_issues={summary['records_with_issues']}")
    print(f"records_without_text={summary['records_without_text']}")
    print(f"duplicate_groups={summary['duplicate_groups']} duplicate_records={summary['duplicate_records']}")
    print(f"json={json_path}")
    print(f"markdown={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
