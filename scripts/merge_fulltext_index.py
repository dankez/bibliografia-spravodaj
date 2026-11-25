#!/usr/bin/env python3
"""Zlúči shardy jedného časopisu z staging adresára do webového fulltext indexu.

Nahradí shardy zadaného journal_id a ponechá shardy ostatných časopisov.
Manifest sa prepočíta zo všetkých shardov, takže zostáva konzistentný.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_DIR = BASE_DIR / "web" / "public" / "data" / "fulltext"
DEFAULT_TARGET_MANIFEST = BASE_DIR / "web" / "public" / "data" / "fulltext_manifest.json"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def shard_stats(path: Path) -> tuple[int, set[int], int]:
    records = read_json(path)
    chars = sum(len(record.get("t", "")) for record in records)
    return len(records), {record["a"] for record in records}, chars


def merge(staging_dir: Path, staging_manifest: Path, target_dir: Path, target_manifest: Path, journal_id: str) -> dict[str, Any]:
    staged = read_json(staging_manifest)
    staged_shards = [shard for shard in staged["shards"] if shard["journal_id"] == journal_id]
    if not staged_shards:
        raise SystemExit(f"Staging neobsahuje shardy pre {journal_id}")

    old = read_json(target_manifest)
    kept = [shard for shard in old["shards"] if shard["journal_id"] != journal_id]

    for old_shard in target_dir.glob(f"{journal_id}/*.json"):
        old_shard.unlink()
    manifest_root = target_manifest.parent
    new_shards: list[dict[str, Any]] = []
    for shard in staged_shards:
        source = staging_dir / shard["path"]
        destination = target_dir / journal_id / Path(shard["path"]).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        new_shards.append(dict(shard, path=destination.relative_to(manifest_root).as_posix()))

    all_shards = kept + new_shards
    all_shards.sort(key=lambda shard: (shard["journal_id"], int(shard["year"]) if str(shard["year"]).isdigit() else 0))

    total_chunks = total_bytes = total_chars = 0
    article_ids: set[int] = set()
    journals: dict[str, dict[str, Any]] = {}
    for shard in all_shards:
        shard_path = target_manifest.parent / shard["path"]
        chunks, ids, chars = shard_stats(shard_path)
        size = shard_path.stat().st_size
        total_chunks += chunks
        total_bytes += size
        total_chars += chars
        article_ids |= ids
        stats = journals.setdefault(shard["journal_id"], {"journal_id": shard["journal_id"], "chunks": 0, "articles": set(), "bytes": 0})
        stats["chunks"] += chunks
        stats["articles"] |= ids
        stats["bytes"] += size
        shard.update(chunks=chunks, articles=len(ids), bytes=size)

    manifest = dict(old)
    manifest.update(
        chunks=total_chunks,
        articles=len(article_ids),
        text_chars=total_chars,
        bytes=total_bytes,
        shards=all_shards,
        journals=[
            {"journal_id": j["journal_id"], "chunks": j["chunks"], "articles": len(j["articles"]), "bytes": j["bytes"]}
            for j in sorted(journals.values(), key=lambda j: j["journal_id"])
        ],
    )
    target_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--staging-manifest", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--target-manifest", type=Path, default=DEFAULT_TARGET_MANIFEST)
    parser.add_argument("--journal", required=True)
    args = parser.parse_args()
    manifest = merge(args.staging_dir, args.staging_manifest, args.target_dir, args.target_manifest, args.journal)
    print(f"shards={len(manifest['shards'])} chunks={manifest['chunks']} articles={manifest['articles']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
