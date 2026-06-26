#!/usr/bin/env python3
"""Apply a structured bibliography errata issue to article JSON files."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA = "sss-bibliografia/article-edit/v1"
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
    "pdf_url",
    "pdf_page_start",
    "pdf_page_end",
}
ARTICLE_PATHS = [
    Path("data/articles_with_urls.json"),
    Path("web/src/data/articles.json"),
]


def clean_text(value: Any, max_length: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max_length]


def normalize_patch_value(field: str, value: Any) -> Any:
    if field in {"authors", "tags", "caves", "groups"}:
        if not isinstance(value, list):
            return []
        return [clean_text(item, 160) for item in value if clean_text(item, 160)][:80]
    if field == "has_map_plan":
        return value is True
    if field in {"year", "pdf_page_start", "pdf_page_end"}:
        if value in (None, ""):
            return None
        try:
            return int(str(value))
        except ValueError:
            return None
    if field == "abstract":
        return str(value or "").replace("\r\n", "\n").strip()[:2000]
    if field == "pdf_url":
        return clean_text(value, 800)
    return clean_text(value, 500)


def normalize_article_patch_object(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {field: normalize_patch_value(field, source.get(field)) for field in ARTICLE_FIELDS}


def normalize_patch(raw_patch: Any) -> dict[str, Any]:
    if not isinstance(raw_patch, dict) or raw_patch.get("schema") != SCHEMA:
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
        "schema": SCHEMA,
        "article_id": article_id,
        "source_version": clean_text(raw_patch.get("source_version"), 120),
        "changed_fields": unique_fields,
        "original": normalize_article_patch_object(raw_patch.get("original")),
        "proposed": normalize_article_patch_object(raw_patch.get("proposed")),
    }


def extract_json_patch(issue_body: str) -> dict[str, Any]:
    match = re.search(r"```json\s*([\s\S]*?)```", issue_body or "", flags=re.IGNORECASE)
    if not match:
        raise ValueError("Issue neobsahuje JSON blok s opravou.")
    return normalize_patch(json.loads(match.group(1)))


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
    changed_files = [str(path) for path in ARTICLE_PATHS if apply_patch_to_file(path, patch)]

    write_output("article_id", patch["article_id"])
    write_output("changed_fields", ",".join(patch["changed_fields"]))
    write_output("changed_files", ",".join(changed_files))
    write_output("source_version", patch["source_version"])
    print(f"Applied issue #{issue_number} for article #{patch['article_id']}.")
    print(f"Changed files: {', '.join(changed_files) if changed_files else 'none'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
