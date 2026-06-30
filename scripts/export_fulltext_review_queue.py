#!/usr/bin/env python3
"""Export a compact fulltext QA incident queue for the web UI."""

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_PATH = BASE_DIR / "reports" / "fulltext_quality_audit.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "web" / "public" / "data" / "fulltext_review_queue.json"
DEFAULT_SUMMARY_OUTPUT_PATH = BASE_DIR / "web" / "src" / "data" / "fulltext_review_summary.json"

ISSUE_LABELS = {
    "empty_text": "Chýba fulltext",
    "very_short_text": "Veľmi krátky text",
    "low_text_density": "Nízka hustota textu",
    "residual_bad_diacritic_tokens": "Podozrivá diakritika",
    "replacement_characters": "Náhradné znaky",
    "control_characters": "Skryté riadiace znaky",
    "private_use_characters": "Private-use znaky",
    "other_hidden_characters": "Iné skryté znaky",
    "cleanup_format_characters": "Formátovacie znaky",
    "cleanup_hyphen_linebreaks": "Delené slová",
    "cleanup_multispace_layout": "Rozťahaný layout",
}

ISSUE_ACTIONS = {
    "empty_text": "Skontrolovať rozsah strán alebo doplniť fulltext.",
    "very_short_text": "Otvoriť PDF a overiť, či nejde len o obálku, reklamu alebo krátku správu.",
    "low_text_density": "Porovnať text s PDF stranou, či nie je posunutý rozsah strán.",
    "residual_bad_diacritic_tokens": "Skontrolovať ukážku textu; pri potvrdení spustiť cielené OCR alebo opraviť text.",
    "replacement_characters": "Nájsť poškodené znaky v texte a porovnať s PDF.",
    "control_characters": "Vyčistiť skryté znaky alebo znovu extrahovať text.",
    "private_use_characters": "Porovnať symboly s PDF a rozhodnúť, či sú dôležité.",
    "other_hidden_characters": "Vyčistiť alebo označiť ako false positive.",
    "cleanup_format_characters": "Kandidát na text-normalizačný pass.",
    "cleanup_hyphen_linebreaks": "Kandidát na spájanie slov cez koniec riadku.",
    "cleanup_multispace_layout": "Kandidát na redukciu viacnásobných medzier.",
}

SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}
AUTO_FIXABLE_ISSUES = {
    "control_characters",
    "cleanup_format_characters",
    "cleanup_hyphen_linebreaks",
    "cleanup_multispace_layout",
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def primary_issue(issues: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        issues,
        key=lambda issue: (SEVERITY_ORDER.get(issue.get("severity"), 0), issue.get("code") or ""),
    )


def compact_link(link: dict[str, Any]) -> dict[str, Any]:
    return {
        "page": link.get("page"),
        "url": link.get("url"),
    }


def human_review_issues(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        issue
        for issue in record.get("issues", [])
        if issue.get("code") not in AUTO_FIXABLE_ISSUES
    ]


def auto_fixable_issue_codes(record: dict[str, Any]) -> list[str]:
    return [
        issue.get("code")
        for issue in record.get("issues", [])
        if issue.get("code") in AUTO_FIXABLE_ISSUES
    ]


def compact_incident(record: dict[str, Any]) -> dict[str, Any]:
    issues = human_review_issues(record)
    primary = primary_issue(issues)
    issue_codes = [issue.get("code") for issue in issues if issue.get("code")]
    return {
        "id": record.get("id"),
        "line": record.get("line"),
        "title": record.get("title"),
        "year": record.get("year"),
        "issue": record.get("issue"),
        "pages": record.get("pages"),
        "status": record.get("status"),
        "text_source": record.get("text_source"),
        "text_chars": record.get("text_chars"),
        "words": record.get("words"),
        "issue_score": record.get("issue_score"),
        "severity": primary.get("severity"),
        "primary_issue": primary.get("code"),
        "primary_label": ISSUE_LABELS.get(primary.get("code"), primary.get("code")),
        "recommended_action": ISSUE_ACTIONS.get(primary.get("code"), "Ručne skontrolovať záznam."),
        "issue_codes": issue_codes,
        "issue_labels": [ISSUE_LABELS.get(code, code) for code in issue_codes],
        "auto_fixable_issue_codes": auto_fixable_issue_codes(record),
        "bad_diacritic_token_examples": record.get("bad_diacritic_token_examples") or [],
        "pdf_links": [compact_link(link) for link in record.get("pdf_page_links", [])],
        "article_url": f"/clanky/{record.get('id')}/" if record.get("id") is not None else "",
    }


def build_queue(audit: dict[str, Any]) -> dict[str, Any]:
    auto_fixable_records_excluded = sum(
        1
        for record in audit.get("records", [])
        if record.get("issues")
        and not record.get("ignored_reason")
        and not human_review_issues(record)
    )
    incidents = [
        compact_incident(record)
        for record in audit.get("records", [])
        if not record.get("ignored_reason") and human_review_issues(record)
    ]
    incidents.sort(
        key=lambda item: (
            -int(item.get("issue_score") or 0),
            -(SEVERITY_ORDER.get(item.get("severity"), 0)),
            int(item.get("year") or 0),
            int(item.get("id") or 0),
        )
    )
    issue_counts = collections.Counter(issue for item in incidents for issue in item.get("issue_codes", []))
    severity_counts = collections.Counter(item.get("severity") for item in incidents)
    years = [int(item["year"]) for item in incidents if str(item.get("year") or "").isdigit()]
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_generated_at": (audit.get("summary") or {}).get("generated_at"),
        "summary": {
            "active_incidents": len(incidents),
            "high": severity_counts.get("high", 0),
            "medium": severity_counts.get("medium", 0),
            "low": severity_counts.get("low", 0),
            "first_year": min(years) if years else None,
            "last_year": max(years) if years else None,
            "ignored_outer_matter": (audit.get("summary") or {}).get("ignored_outer_matter_records", 0),
            "records_without_text": (audit.get("summary") or {}).get("records_without_text", 0),
            "duplicate_article_ids": (audit.get("summary") or {}).get("duplicate_article_ids", 0),
            "auto_fixable_records_excluded": auto_fixable_records_excluded,
            "issue_counts": dict(issue_counts),
        },
        "issue_labels": ISSUE_LABELS,
        "incidents": incidents,
    }


def build_summary(queue: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": queue.get("generated_at"),
        "source_generated_at": queue.get("source_generated_at"),
        "summary": queue.get("summary") or {},
        "issue_labels": queue.get("issue_labels") or {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export fulltext QA incident queue for Astro.")
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT_PATH)
    args = parser.parse_args()

    if not args.audit.exists():
        print(f"Missing audit report: {args.audit}", file=sys.stderr)
        return 1

    queue = build_queue(read_json(args.audit))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(build_summary(queue), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"active_incidents={queue['summary']['active_incidents']}")
    print(f"output={args.output}")
    print(f"summary_output={args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
