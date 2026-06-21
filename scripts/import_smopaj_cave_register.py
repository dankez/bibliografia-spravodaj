#!/usr/bin/env python3
"""Parse official SMOPaJ cave register PDFs converted with pdftotext."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_GEOMORPHOLOGY_TEXT = BASE_DIR / "data" / "source_text" / "smopaj_zoznam_jaskyn_2017.txt"
DEFAULT_NAME_REGISTER_TEXT = BASE_DIR / "data" / "source_text" / "smopaj_register_jaskyn.txt"
DEFAULT_OUTPUT = BASE_DIR / "data" / "smopaj_cave_register_2017.json"
SOURCES = [
    {
        "title": "Zoznam jaskýň k 31.12.2017 podľa geomorfologických jednotiek",
        "url": "https://www.smopaj.sk/sk/documentloader.php?id=1938&filename=zoznam%20jask%C3%BD%C5%88%20k%2031%2012%202017.pdf",
    },
    {
        "title": "Register jaskýň",
        "url": "https://www.smopaj.sk/sk/documentloader.php?id=1939&filename=register%20jask%C3%BD%C5%88.pdf",
    },
    {
        "title": "Zoznam podľa geomorfologických celkov",
        "url": "https://www.smopaj.sk/sk/documentloader.php?id=1940&filename=zoznam%20pod%C4%BEa%20geomorfologick%C3%BDch%20celkov.pdf",
    },
]


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_registry_number(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    text = text.rstrip(".")
    return text


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        key = normalize_text(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def is_noise_line(line: str) -> bool:
    clean = line.strip()
    if not clean:
        return True
    if not normalize_text(clean):
        return True
    if clean.startswith("Page ") or re.fullmatch(r"Page \d+ of \d+", clean):
        return True
    if clean in {"REGISTER JASKÝŇ", "Názov                                 Číslo jaskyne"}:
        return True
    if "Zoznam jaskýň k 31.12.2017" in clean or "podľa geomorfologických jednotiek" in clean:
        return True
    return False


ENTRY_START_RE = re.compile(r"^\s*(?P<list_number>\d+)\.\s+(?:(?P<component_number>\d+)\.\s+)?(?P<body>.+)")
REGISTRY_NUMBER_RE = re.compile(r"r\.\s*č\.\s*(?P<number>\d[\d\s]*(?:\.\s*\d+\.)?)")


def parse_heading(line: str) -> dict[str, str]:
    parts = [part.strip() for part in line.split(",") if part.strip()]
    if not parts:
        return {}
    heading = {
        "geomorph_celok": parts[0],
        "geomorph_podcelok": parts[1] if len(parts) > 1 else "",
        "geomorph_cast": parts[2] if len(parts) > 2 else "",
    }
    return heading


def split_name_and_aliases(raw_name: str) -> tuple[str, list[str]]:
    text = re.sub(r"\s+", " ", raw_name).strip()
    aliases: list[str] = []

    def collect_aliases(match: re.Match[str]) -> str:
        aliases.extend(part.strip() for part in match.group(1).split(",") if part.strip())
        return ""

    official = re.sub(r"\(([^)]*)\)", collect_aliases, text)
    official = re.sub(r"\s+", " ", official).strip(" -")
    return official, unique_strings(aliases)


def parse_record(lines: list[str], heading: dict[str, str]) -> dict[str, Any] | None:
    if not lines:
        return None
    first_line = lines[0].replace("\f", "").strip()
    match = ENTRY_START_RE.match(first_line)
    if not match:
        return None

    body_lines = [match.group("body"), *lines[1:]]
    record_text = re.sub(r"\s+", " ", " ".join(line.strip() for line in body_lines)).strip()
    name_boundary = re.search(r"\s+-\s+k\.\s*ú\.", record_text)
    name_segment = record_text[: name_boundary.start()].strip() if name_boundary else record_text.split(" - ", 1)[0].strip()
    official_name, aliases = split_name_and_aliases(name_segment)
    if not official_name:
        return None

    cave_number = normalize_registry_number(
        f"{match.group('list_number')}.{match.group('component_number')}"
        if match.group("component_number")
        else match.group("list_number")
    )
    registry_match = REGISTRY_NUMBER_RE.search(record_text)
    registry_number = normalize_registry_number(registry_match.group("number")) if registry_match else cave_number

    return {
        "cave_number": cave_number,
        "registry_number": registry_number,
        "list_number": normalize_registry_number(match.group("list_number")),
        "official_name": official_name,
        "aliases": aliases,
        "geomorph_celok": heading.get("geomorph_celok", ""),
        "geomorph_podcelok": heading.get("geomorph_podcelok", ""),
        "geomorph_cast": heading.get("geomorph_cast", ""),
        "raw_heading": ", ".join(part for part in (heading.get("geomorph_celok"), heading.get("geomorph_podcelok"), heading.get("geomorph_cast")) if part),
    }


def parse_geomorphology_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    heading: dict[str, str] = {}
    current: list[str] = []

    for raw_line in text.replace("\f", "\n").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if is_noise_line(stripped):
            continue

        current_text = " ".join(current)
        looks_like_heading = (
            len(stripped) <= 90
            and " - " not in stripped
            and " r. č." not in stripped
            and not stripped.startswith("[")
            and not re.search(r"\d", stripped)
            and (not current or bool(REGISTRY_NUMBER_RE.search(current_text)))
        )
        if looks_like_heading:
            record = parse_record(current, heading)
            if record:
                entries.append(record)
            current = []
            heading = parse_heading(stripped)
            continue

        if ENTRY_START_RE.match(stripped):
            record = parse_record(current, heading)
            if record:
                entries.append(record)
            current = [stripped]
            continue

        if current:
            current.append(stripped)

    record = parse_record(current, heading)
    if record:
        entries.append(record)
    return entries


REGISTER_LINE_RE = re.compile(r"^\s*(?P<name>.+?)\s+(?P<number>\d[\d\s]*(?:\.\d+\.)?)\s*$")


def parse_name_register(text: str) -> dict[str, list[str]]:
    names_by_number: dict[str, list[str]] = {}
    for raw_line in text.replace("\f", "\n").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if is_noise_line(stripped):
            continue
        match = REGISTER_LINE_RE.match(line)
        if not match:
            continue
        name = re.sub(r"\s+", " ", match.group("name")).strip()
        number = normalize_registry_number(match.group("number"))
        if not name or not number:
            continue
        names_by_number.setdefault(number, [])
        names_by_number[number] = unique_strings([*names_by_number[number], name])
    return names_by_number


def merge_name_register(entries: list[dict[str, Any]], names_by_number: dict[str, list[str]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for entry in entries:
        names = unique_strings(
            [
                entry.get("official_name", ""),
                *list(entry.get("aliases") or []),
                *names_by_number.get(str(entry.get("cave_number") or ""), []),
            ]
        )
        item = dict(entry)
        item["names"] = names
        merged.append(item)
    return merged


def build_output(geomorphology_text: str, name_register_text: str) -> dict[str, Any]:
    entries = parse_geomorphology_entries(geomorphology_text)
    names_by_number = parse_name_register(name_register_text)
    merged_entries = merge_name_register(entries, names_by_number)
    return {
        "schema_version": "smopaj-cave-register/v1",
        "sources": SOURCES,
        "entries": merged_entries,
        "stats": {
            "entries": len(merged_entries),
            "name_register_numbers": len(names_by_number),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geomorphology-text", type=Path, default=DEFAULT_GEOMORPHOLOGY_TEXT)
    parser.add_argument("--name-register-text", type=Path, default=DEFAULT_NAME_REGISTER_TEXT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    geomorphology_text = args.geomorphology_text.read_text(encoding="utf-8")
    name_register_text = args.name_register_text.read_text(encoding="utf-8")
    output = build_output(geomorphology_text, name_register_text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **output["stats"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
