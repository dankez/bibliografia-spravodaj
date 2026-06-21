#!/usr/bin/env python3
"""Export compact fulltext chunks for lazy browser-side MiniSearch."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_PATH = BASE_DIR / "data" / "research_chunks.jsonl"
DEFAULT_OUTPUT_DIR = BASE_DIR / "web" / "public" / "data" / "fulltext"
DEFAULT_MANIFEST_PATH = BASE_DIR / "web" / "public" / "data" / "fulltext_manifest.json"
DEFAULT_JOURNAL_ID = "spravodaj_sss"


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc


def safe_path_part(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text).strip("-")
    return text or fallback


def compact_chunk(record: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
    chunk_id = str(record.get("chunk_id") or "").strip()
    article_id = record.get("article_id")
    text = str(record.get("text") or "").strip()
    if not chunk_id or not isinstance(article_id, int) or not text:
        return None
    journal_id = safe_path_part(record.get("journal_id"), DEFAULT_JOURNAL_ID)
    year = safe_path_part(record.get("year"), "unknown")
    return journal_id, year, {"id": chunk_id, "a": article_id, "t": text}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def export_index(chunks_path: Path, output_dir: Path, manifest_path: Path) -> dict[str, Any]:
    shards: dict[tuple[str, str], list[dict[str, Any]]] = {}
    article_ids: set[int] = set()
    text_chars = 0

    for record in iter_jsonl(chunks_path):
        compact = compact_chunk(record)
        if compact is None:
            continue
        journal_id, year, payload = compact
        shards.setdefault((journal_id, year), []).append(payload)
        article_ids.add(payload["a"])
        text_chars += len(payload["t"])

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_path in output_dir.glob("**/*.json"):
        stale_path.unlink()

    shard_manifest: list[dict[str, Any]] = []
    total_bytes = 0
    by_journal: dict[str, dict[str, Any]] = {}
    for (journal_id, year), records in sorted(shards.items()):
        shard_path = output_dir / journal_id / f"{year}.json"
        shard_path.parent.mkdir(parents=True, exist_ok=True)
        with shard_path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, separators=(",", ":"))
        article_count = len({record["a"] for record in records})
        byte_count = shard_path.stat().st_size
        total_bytes += byte_count
        relative = shard_path.relative_to(manifest_path.parent)
        shard_manifest.append(
            {
                "journal_id": journal_id,
                "year": int(year) if year.isdigit() else year,
                "path": str(relative),
                "chunks": len(records),
                "articles": article_count,
                "bytes": byte_count,
            }
        )
        journal_stats = by_journal.setdefault(journal_id, {"journal_id": journal_id, "chunks": 0, "articles": set(), "bytes": 0})
        journal_stats["chunks"] += len(records)
        journal_stats["articles"].update(record["a"] for record in records)
        journal_stats["bytes"] += byte_count

    journal_manifest = []
    for journal_id, stats in sorted(by_journal.items()):
        journal_manifest.append(
            {
                "journal_id": journal_id,
                "chunks": stats["chunks"],
                "articles": len(stats["articles"]),
                "bytes": stats["bytes"],
            }
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 2,
        "source": display_path(chunks_path),
        "index_dir": display_path(output_dir),
        "chunks": sum(len(records) for records in shards.values()),
        "articles": len(article_ids),
        "text_chars": text_chars,
        "bytes": total_bytes,
        "journals": journal_manifest,
        "shards": shard_manifest,
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()

    manifest = export_index(args.chunks, args.output_dir, args.manifest)
    print(
        "Exported fulltext web index: "
        f"chunks={manifest['chunks']}, articles={manifest['articles']}, "
        f"shards={len(manifest['shards'])}, bytes={manifest['bytes']}, output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
