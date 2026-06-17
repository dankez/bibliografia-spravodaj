#!/usr/bin/env python3
"""Export compact fulltext chunks for lazy browser-side MiniSearch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_PATH = BASE_DIR / "data" / "research_chunks.jsonl"
DEFAULT_OUTPUT_PATH = BASE_DIR / "web" / "public" / "data" / "fulltext_index.json"
DEFAULT_MANIFEST_PATH = BASE_DIR / "web" / "public" / "data" / "fulltext_manifest.json"


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc


def compact_chunk(record: dict[str, Any]) -> dict[str, Any] | None:
    chunk_id = str(record.get("chunk_id") or "").strip()
    article_id = record.get("article_id")
    text = str(record.get("text") or "").strip()
    if not chunk_id or not isinstance(article_id, int) or not text:
        return None
    return {
        "id": chunk_id,
        "a": article_id,
        "t": text,
    }


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def export_index(chunks_path: Path, output_path: Path, manifest_path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    article_ids: set[int] = set()
    text_chars = 0

    for record in iter_jsonl(chunks_path):
        compact = compact_chunk(record)
        if compact is None:
            continue
        records.append(compact)
        article_ids.add(compact["a"])
        text_chars += len(compact["t"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, separators=(",", ":"))

    manifest = {
        "source": display_path(chunks_path),
        "index": display_path(output_path),
        "chunks": len(records),
        "articles": len(article_ids),
        "text_chars": text_chars,
        "bytes": output_path.stat().st_size,
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()

    manifest = export_index(args.chunks, args.output, args.manifest)
    print(
        "Exported fulltext web index: "
        f"chunks={manifest['chunks']}, articles={manifest['articles']}, "
        f"bytes={manifest['bytes']}, output={args.output}"
    )


if __name__ == "__main__":
    main()
