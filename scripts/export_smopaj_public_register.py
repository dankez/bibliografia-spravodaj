#!/usr/bin/env python3
"""Export a compact public SMOPaJ cave register search index for the web UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "data" / "smopaj_cave_register_2017.json"
DEFAULT_CAVES_INPUT = BASE_DIR / "web" / "src" / "data" / "caves.json"
DEFAULT_OUTPUT = BASE_DIR / "web" / "public" / "data" / "smopaj_cave_register_2017_search.json"


def unique_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = " ".join(text.casefold().split())
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def build_aliases_by_cave_number(caves: list[dict[str, Any]]) -> dict[str, list[str]]:
    aliases_by_number: dict[str, list[str]] = {}
    for cave in caves:
        cave_number = str(cave.get("smopaj_cave_number") or "").strip()
        if not cave_number:
            continue
        aliases_by_number.setdefault(cave_number, []).extend([cave.get("name"), *(cave.get("aliases") or [])])
    return {key: unique_texts(values) for key, values in aliases_by_number.items()}


def build_public_entry(entry: dict[str, Any], bibliography_aliases: list[str] | None = None) -> dict[str, Any]:
    names = unique_texts(
        [
            entry.get("official_name"),
            *(entry.get("names") or []),
            *(entry.get("aliases") or []),
            *(bibliography_aliases or []),
        ]
    )
    return {
        "cave_number": str(entry.get("cave_number") or "").strip(),
        "registry_number": str(entry.get("registry_number") or "").strip(),
        "official_name": str(entry.get("official_name") or "").strip(),
        "names": names,
        "geomorph_celok": str(entry.get("geomorph_celok") or "").strip(),
        "geomorph_podcelok": str(entry.get("geomorph_podcelok") or "").strip(),
        "geomorph_cast": str(entry.get("geomorph_cast") or "").strip(),
    }


def build_public_register(data: dict[str, Any], caves: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    aliases_by_number = build_aliases_by_cave_number(caves or [])
    entries = [
        build_public_entry(entry, aliases_by_number.get(str(entry.get("cave_number") or "").strip()))
        for entry in data.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("cave_number") or "").strip()
    ]
    entries.sort(key=lambda item: [int(part) if part.isdigit() else part for part in item["cave_number"].split(".")])
    return {
        "schema_version": "smopaj-cave-public-search/v1",
        "source": "Zoznam jaskýň k 31.12.2017 podľa geomorfologických jednotiek",
        "source_url": "https://www.smopaj.sk/sk/documentloader.php?id=1938&filename=zoznam%20jask%C3%BD%C5%88%20k%2031%2012%202017.pdf",
        "entries": entries,
        "stats": {
            "entries": len(entries),
        },
    }


def main() -> None:
    data = json.loads(DEFAULT_INPUT.read_text(encoding="utf-8"))
    caves = json.loads(DEFAULT_CAVES_INPUT.read_text(encoding="utf-8")) if DEFAULT_CAVES_INPUT.exists() else []
    public_register = build_public_register(data, caves if isinstance(caves, list) else [])
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(
        json.dumps(public_register, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(DEFAULT_OUTPUT),
                "entries": public_register["stats"]["entries"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
