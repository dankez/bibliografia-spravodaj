#!/usr/bin/env python3
"""Apply a structured bibliography errata issue to article JSON files."""

from __future__ import annotations

import json
import os
import re
import sys
import datetime as dt
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import export_fulltext_review_queue as review_exporter

ARTICLE_EDIT_SCHEMA = "sss-bibliografia/article-edit/v1"
FULLTEXT_REVIEW_SCHEMA = "sss-bibliografia/fulltext-review/v1"
FULLTEXT_REVIEW_DECISIONS_SCHEMA = "sss-bibliografia/fulltext-review-decisions/v1"
ARTICLE_FIELDS = {
    "title",
    "authors",
    "journal_id",
    "journal_title",
    "journal_short_title",
    "year",
    "volume",
    "issue",
    "pages",
    "abstract",
    "tags",
    "caves",
    "groups",
    "has_map_plan",
    "map_plan_pages",
    "map_plan_score",
    "pdf_url",
    "pdf_page_start",
    "pdf_page_end",
    "pdf_page_offset",
    "caves_verified",
    "wikidata",
    "cover_url",
}
ARTICLE_PATHS = [
    Path("data/articles_with_urls.json"),
    Path("web/src/data/articles.json"),
]
FULLTEXT_REVIEW_DECISIONS_PATH = Path("data/fulltext_review_decisions.json")
FULLTEXT_REVIEW_QUEUE_PATH = Path("web/public/data/fulltext_review_queue.json")
FULLTEXT_REVIEW_SUMMARY_PATH = Path("web/src/data/fulltext_review_summary.json")


def clean_text(value: Any, max_length: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max_length]


def normalize_patch_value(field: str, value: Any) -> Any:
    if field in {"authors", "tags", "caves", "groups"}:
        if not isinstance(value, list):
            return []
        return [clean_text(item, 160) for item in value if clean_text(item, 160)][:80]
    if field == "map_plan_pages":
        if not isinstance(value, list):
            return []
        pages = []
        for item in value:
            try:
                pages.append(int(str(item)))
            except ValueError:
                continue
        return pages[:80]
    if field == "wikidata":
        return value[:80] if isinstance(value, list) else []
    if field in {"has_map_plan", "caves_verified"}:
        return value is True
    if field in {"year", "pdf_page_start", "pdf_page_end", "pdf_page_offset", "map_plan_score"}:
        if value in (None, ""):
            return None
        try:
            return int(str(value))
        except ValueError:
            return None
    if field == "abstract":
        return str(value or "").replace("\r\n", "\n").strip()[:2000]
    if field in {"pdf_url", "cover_url"}:
        return clean_text(value, 800)
    return clean_text(value, 500)


def normalize_article_patch_object(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {field: normalize_patch_value(field, source.get(field)) for field in ARTICLE_FIELDS}


def normalize_article_patch(raw_patch: Any) -> dict[str, Any]:
    if not isinstance(raw_patch, dict) or raw_patch.get("schema") != ARTICLE_EDIT_SCHEMA:
        raise ValueError("Issue neobsahuje platný JSON diff článku.")
    changed_fields = raw_patch.get("changed_fields") if isinstance(raw_patch.get("changed_fields"), list) else []
    unique_fields = []
    for field in changed_fields:
        normalized = clean_text(field, 80)
        if normalized in ARTICLE_FIELDS and normalized not in unique_fields:
            unique_fields.append(normalized)
    if not unique_fields:
        raise ValueError("JSON diff neobsahuje žiadne podporované zmenené pole.")
    article_id = clean_text(raw_patch.get("article_id"), 40)
    if not article_id.isdigit():
        raise ValueError("JSON diff neobsahuje platné ID článku.")
    return {
        "schema": ARTICLE_EDIT_SCHEMA,
        "article_id": article_id,
        "source_version": clean_text(raw_patch.get("source_version"), 120),
        "changed_fields": unique_fields,
        "original": normalize_article_patch_object(raw_patch.get("original")),
        "proposed": normalize_article_patch_object(raw_patch.get("proposed")),
    }


def normalize_string_list(value: Any, max_items: int = 30, max_length: int = 180) -> list[str]:
    if not isinstance(value, list):
        return []
    return [clean_text(item, max_length) for item in value if clean_text(item, max_length)][:max_items]


def normalize_fulltext_review(raw_patch: Any) -> dict[str, Any]:
    if not isinstance(raw_patch, dict) or raw_patch.get("schema") != FULLTEXT_REVIEW_SCHEMA:
        raise ValueError("Issue neobsahuje platné JSON rozhodnutie kontroly fulltextu.")
    decision = clean_text(raw_patch.get("decision"), 40)
    if decision not in {"ok", "rejected", "needs_fix"}:
        raise ValueError("Rozhodnutie kontroly fulltextu nemá podporovanú hodnotu.")
    article_id = clean_text(raw_patch.get("article_id"), 40)
    if not article_id.isdigit():
        raise ValueError("Rozhodnutie kontroly fulltextu neobsahuje platné ID článku.")
    decision_key = clean_text(raw_patch.get("decision_key"), 180)
    if not decision_key:
        raise ValueError("Rozhodnutie kontroly fulltextu neobsahuje identifikátor incidentu.")
    return {
        "schema": FULLTEXT_REVIEW_SCHEMA,
        "decision": decision,
        "decision_key": decision_key,
        "article_id": article_id,
        "article_title": clean_text(raw_patch.get("article_title"), 260),
        "article_url": clean_text(raw_patch.get("article_url"), 500),
        "year": clean_text(raw_patch.get("year"), 40),
        "pages": clean_text(raw_patch.get("pages"), 80),
        "primary_issue": clean_text(raw_patch.get("primary_issue"), 120),
        "primary_label": clean_text(raw_patch.get("primary_label"), 180),
        "issue_codes": normalize_string_list(raw_patch.get("issue_codes"), 30, 120),
        "issue_labels": normalize_string_list(raw_patch.get("issue_labels"), 30, 180),
        "issue_score": clean_text(raw_patch.get("issue_score"), 40),
        "text_status": clean_text(raw_patch.get("text_status"), 120),
        "text_source": clean_text(raw_patch.get("text_source"), 120),
        "text_chars": clean_text(raw_patch.get("text_chars"), 40),
        "words": clean_text(raw_patch.get("words"), 40),
        "recommended_action": clean_text(raw_patch.get("recommended_action"), 500),
        "pdf_url": clean_text(raw_patch.get("pdf_url"), 800),
        "source_generated_at": clean_text(raw_patch.get("source_generated_at"), 120),
        "source_version": clean_text(raw_patch.get("source_version"), 120),
    }


def extract_json_patch(issue_body: str) -> dict[str, Any]:
    match = re.search(r"```json\s*([\s\S]*?)```", issue_body or "", flags=re.IGNORECASE)
    if not match:
        raise ValueError("Issue neobsahuje JSON blok s opravou.")
    raw_patch = json.loads(match.group(1))
    schema = raw_patch.get("schema") if isinstance(raw_patch, dict) else ""
    if schema == ARTICLE_EDIT_SCHEMA:
        return normalize_article_patch(raw_patch)
    if schema == FULLTEXT_REVIEW_SCHEMA:
        return normalize_fulltext_review(raw_patch)
    raise ValueError("Issue neobsahuje podporovaný štruktúrovaný JSON blok.")


def github_api(path: str, token: str, repo: str) -> Any:
    url = f"https://api.github.com{path.format(repository=repo)}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "sss-bibliografia-admin-action",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API zlyhalo ({error.code}): {detail}") from error


def comparable_value(article: dict[str, Any], field: str) -> Any:
    defaults = {
        "journal_id": "spravodaj_sss",
        "journal_title": "Spravodaj Slovenskej speleologickej spoločnosti",
        "journal_short_title": "Spravodaj SSS",
    }
    return normalize_patch_value(field, article[field] if field in article else defaults.get(field))


def apply_patch_to_file(path: Path, patch: dict[str, Any]) -> bool:
    original_text = path.read_text(encoding="utf-8")
    articles = json.loads(original_text)
    if not isinstance(articles, list):
        raise ValueError(f"{path} nemá očakávaný formát poľa článkov.")

    article = next((item for item in articles if str(item.get("id")) == patch["article_id"]), None)
    if article is None:
        raise ValueError(f"Článok #{patch['article_id']} sa nenašiel v {path}.")

    conflicting = [
        field
        for field in patch["changed_fields"]
        if comparable_value(article, field) != patch["original"][field]
    ]
    if conflicting:
        raise ValueError(f"Aktuálne dáta sa zmenili od nahlásenia. Konflikt v {path}: {', '.join(conflicting)}")

    for field in patch["changed_fields"]:
        article[field] = patch["proposed"][field]

    updated_text = json.dumps(articles, ensure_ascii=False, indent=2) + "\n"
    if updated_text == original_text:
        return False
    path.write_text(updated_text, encoding="utf-8")
    return True


def read_decisions(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": FULLTEXT_REVIEW_DECISIONS_SCHEMA, "decisions": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"schema_version": FULLTEXT_REVIEW_DECISIONS_SCHEMA, "decisions": []}
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    return {"schema_version": FULLTEXT_REVIEW_DECISIONS_SCHEMA, "decisions": decisions}


def write_json_if_changed(path: Path, payload: Any) -> bool:
    original_text = path.read_text(encoding="utf-8") if path.exists() else ""
    updated_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if updated_text == original_text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated_text, encoding="utf-8")
    return True


def regenerate_fulltext_review_queue(decisions: dict[str, Any]) -> list[str]:
    if not review_exporter.DEFAULT_AUDIT_PATH.exists():
        return []
    queue = review_exporter.build_queue(review_exporter.read_json(review_exporter.DEFAULT_AUDIT_PATH), decisions)
    changed_files = []
    if write_json_if_changed(FULLTEXT_REVIEW_QUEUE_PATH, queue):
        changed_files.append(str(FULLTEXT_REVIEW_QUEUE_PATH))
    if write_json_if_changed(FULLTEXT_REVIEW_SUMMARY_PATH, review_exporter.build_summary(queue)):
        changed_files.append(str(FULLTEXT_REVIEW_SUMMARY_PATH))
    return changed_files


def apply_fulltext_review_decision(patch: dict[str, Any], issue_number: str) -> list[str]:
    decisions_payload = read_decisions(FULLTEXT_REVIEW_DECISIONS_PATH)
    decisions = [
        item
        for item in decisions_payload.get("decisions", [])
        if str(item.get("decision_key") or "") != patch["decision_key"]
    ]
    decisions.append(
        {
            **patch,
            "schema": FULLTEXT_REVIEW_SCHEMA,
            "issue_number": clean_text(issue_number, 40),
            "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    decisions.sort(key=lambda item: (str(item.get("article_id") or ""), str(item.get("primary_issue") or ""), str(item.get("decision_key") or "")))
    updated_payload = {
        "schema_version": FULLTEXT_REVIEW_DECISIONS_SCHEMA,
        "decisions": decisions,
    }
    changed_files = []
    if write_json_if_changed(FULLTEXT_REVIEW_DECISIONS_PATH, updated_payload):
        changed_files.append(str(FULLTEXT_REVIEW_DECISIONS_PATH))
    changed_files.extend(regenerate_fulltext_review_queue(updated_payload))
    return changed_files


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    if not token or not repo or not issue_number:
        raise RuntimeError("Chýba GITHUB_TOKEN, GITHUB_REPOSITORY alebo ISSUE_NUMBER.")

    issue = github_api(f"/repos/{{repository}}/issues/{issue_number}", token, repo)
    patch = extract_json_patch(issue.get("body", ""))
    if patch["schema"] == ARTICLE_EDIT_SCHEMA:
        changed_files = [str(path) for path in ARTICLE_PATHS if apply_patch_to_file(path, patch)]
        changed_fields = ",".join(patch["changed_fields"])
        structured_type = "article_edit"
    elif patch["schema"] == FULLTEXT_REVIEW_SCHEMA:
        changed_files = apply_fulltext_review_decision(patch, issue_number)
        changed_fields = patch["decision"]
        structured_type = "fulltext_review"
    else:
        raise ValueError("Nepodporovaná schéma opravy.")

    write_output("article_id", patch["article_id"])
    write_output("changed_fields", changed_fields)
    write_output("changed_files", ",".join(changed_files))
    write_output("source_version", patch["source_version"])
    write_output("structured_type", structured_type)
    print(f"Applied issue #{issue_number} for article #{patch['article_id']} ({structured_type}).")
    print(f"Changed files: {', '.join(changed_files) if changed_files else 'none'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
