#!/usr/bin/env python3
"""AI-assisted matching of bibliography cave cards to the SMOPaJ cave register.

The script is intentionally conservative. It creates a separate generated
match file that is merged after manually curated overrides by build_cave_index.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

import build_cave_index as cave_index
from codex_ai_backend import CodexBackendError, run_codex_json


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CAVES_PATH = BASE_DIR / "web" / "src" / "data" / "caves.json"
DEFAULT_REGISTER_PATH = BASE_DIR / "data" / "smopaj_cave_register_2017.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "data" / "smopaj_cave_ai_matches.json"
DEFAULT_FULLTEXT_PATH = BASE_DIR / "data" / "article_fulltext.jsonl"
DEFAULT_MODEL = "gemma4:e2b-it-qat"
OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"
MAX_CONTEXT_CHARS = 18000
MAX_ARTICLE_TEXT_CHARS = 2600

CAVE_TYPE_TOKENS = {
    "jaskyna",
    "jaskyne",
    "jaskyni",
    "jaskynu",
    "jaskynou",
    "jaskyn",
    "jeskyne",
    "jeskyne",
    "cave",
    "priepast",
    "priepasti",
    "diera",
    "diery",
    "jama",
    "vyvieracka",
    "ponor",
    "sifon",
}
GENERIC_CAVE_CARD_TOKENS = {
    "objav",
    "objavy",
    "nova",
    "nove",
    "novy",
    "jaskyn",
    "jaskyna",
    "jaskyne",
    "poloha",
    "lokalizacia",
    "vyskum",
    "prieskum",
    "mapovanie",
    "starostlivost",
    "prakticka",
    "pseudokrasove",
    "pobrezne",
    "ladove",
    "priepastovita",
}
GENERIC_CAVE_CARD_PHRASES = {
    "1987",
    "2016",
    "charakter jaskyne",
    "charakteristika jaskyne",
    "dlhodoby pobyt",
    "ladove jaskyne",
    "lokalizacia jaskyne",
    "najvacsia jaskyna",
    "nova jaskyna",
    "nova pseudokrasova jaskyna",
    "nova velka jaskyna",
    "novy objav",
    "objav jaskyne",
    "objav novej jaskyne",
    "objav priepasti",
    "objavy",
    "pobrezne jaskyne",
    "poloha jaskyne",
    "prakticka starostlivost o jaskyne",
    "priepastovita jaskyna",
    "pseudokrasove jaskyne",
    "starostlivost o jaskyne",
    "strucne o jaskyni",
    "strucne o priepasti",
    "strucne o prieskume jaskyne",
    "vyuzitie jaskyne",
    "znovuotvorenie jaskyne",
}
FOREIGN_CONTEXT_TOKENS = {
    "kosovo",
    "prokletije",
    "venezuel",
    "mexik",
    "chorvatsk",
    "croatia",
    "slovacka jama",
    "velika klisura",
    "alban",
    "macedonsk",
    "kuwait",
    "spanielsk",
    "francuzsk",
    "polsk",
    "cesk",
    "moravsk",
}
SLOVAK_CONTEXT_TOKENS = {
    "slovensk",
    "tatry",
    "fatra",
    "kras",
    "planina",
    "dolina",
    "vrchy",
    "hornatina",
    "pohorie",
    "raj",
    "liptov",
    "spis",
    "gemer",
}

AI_DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["match", "defer"]},
        "cave_number": {"type": "string"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["decision", "cave_number", "confidence", "reason"],
}


def normalize(value: Any) -> str:
    return cave_index.normalize_text(value)


def slugify(value: Any) -> str:
    return cave_index.slugify(value)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unique(values: list[str]) -> list[str]:
    return cave_index.unique_strings(values)


def stem_token(token: str) -> str:
    token = normalize(token)
    for suffix in (
        "iach",
        "ach",
        "skeho",
        "skemu",
        "skej",
        "skou",
        "skych",
        "skymi",
        "ych",
        "ovej",
        "ovou",
        "oveho",
        "om",
        "ou",
        "ej",
        "ho",
        "mu",
        "mi",
        "ch",
        "a",
        "e",
        "i",
        "u",
        "y",
    ):
        if len(token) - len(suffix) >= 4 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def name_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    for token in normalize(value).split():
        stem = stem_token(token)
        if not stem or stem in CAVE_TYPE_TOKENS:
            continue
        tokens.append(stem)
    return tokens


def comparable_name(value: Any) -> str:
    return " ".join(name_tokens(value))


def entry_names(entry: dict[str, Any]) -> list[str]:
    return unique(
        [
            str(entry.get("official_name") or ""),
            *[str(item or "") for item in entry.get("names") or []],
            *[str(item or "") for item in entry.get("aliases") or []],
        ]
    )


def entry_name_token_set(entry: dict[str, Any]) -> set[str]:
    cached = entry.get("_ai_match_name_tokens")
    if isinstance(cached, set):
        return cached
    tokens: set[str] = set()
    for entry_name in entry_names(entry):
        tokens.update(name_tokens(entry_name))
    entry["_ai_match_name_tokens"] = tokens
    return tokens


def entry_region_text(entry: dict[str, Any]) -> str:
    return " ".join(
        str(entry.get(key) or "")
        for key in (
            "geomorph_celok",
            "geomorph_podcelok",
            "geomorph_cast",
            "raw_heading",
        )
    )


def cave_summary_context(cave: dict[str, Any], fulltext_by_id: dict[int, str] | None = None) -> str:
    chunks = [
        f"Názov karty: {cave.get('name', '')}",
        f"Alias: {', '.join(cave.get('aliases') or [])}",
        f"Oblasť v registri webu: {cave.get('area', '')}",
    ]
    for article in cave.get("articles") or []:
        article_id = int(article.get("id") or 0)
        chunks.append(
            "\n".join(
                [
                    f"Článok {article_id}: {article.get('title', '')}",
                    f"Rok/časopis/číslo/strany: {article.get('year')} / {article.get('journal_short_title', '')} / {article.get('issue', '')} / {article.get('pages', '')}",
                    f"Anotácia: {article.get('abstract', '')}",
                ]
            )
        )
        if fulltext_by_id and article_id in fulltext_by_id:
            text = re.sub(r"\s+", " ", fulltext_by_id[article_id]).strip()
            if text:
                chunks.append(f"Text článku {article_id}: {text[:MAX_ARTICLE_TEXT_CHARS]}")
        if sum(len(chunk) for chunk in chunks) > MAX_CONTEXT_CHARS:
            break
    context = "\n\n".join(chunk for chunk in chunks if chunk.strip())
    return context[:MAX_CONTEXT_CHARS]


def name_similarity(cave_name: str, entry: dict[str, Any]) -> float:
    cave_comp = comparable_name(cave_name)
    cave_norm = normalize(cave_name)
    best = 0.0
    cave_tokens = set(name_tokens(cave_name))
    for entry_name in entry_names(entry):
        entry_comp = comparable_name(entry_name)
        if cave_comp and entry_comp:
            best = max(best, difflib.SequenceMatcher(None, cave_comp, entry_comp).ratio())
        best = max(best, difflib.SequenceMatcher(None, cave_norm, normalize(entry_name)).ratio())
        entry_tokens = set(name_tokens(entry_name))
        if cave_tokens and entry_tokens:
            intersection = len(cave_tokens & entry_tokens)
            union = len(cave_tokens | entry_tokens)
            best = max(best, intersection / union)
    return best


def context_region_score(context: str, entry: dict[str, Any]) -> float:
    context_key = normalize(context)
    context_stems = {stem_token(token) for token in context_key.split() if len(token) > 3}
    score = 0.0
    for value in (
        entry.get("geomorph_celok"),
        entry.get("geomorph_podcelok"),
        entry.get("geomorph_cast"),
        entry.get("raw_heading"),
    ):
        region = normalize(value)
        if not region:
            continue
        if region in context_key:
            score += 2.5
            continue
        tokens = [token for token in region.split() if len(token) > 3]
        if tokens:
            token_stems = [stem_token(token) for token in tokens]
            hits = sum(1 for token in token_stems if token in context_stems or token in context_key)
            score += hits / len(tokens)
    return score


def cave_is_probably_foreign_or_generic(cave: dict[str, Any]) -> str:
    context = normalize(cave_summary_context(cave))
    name_key = normalize(cave.get("name") or "")
    tokens = set(name_tokens(cave.get("name") or ""))
    if name_key in GENERIC_CAVE_CARD_PHRASES:
        return "generická alebo skupinová karta bez jednoznačného názvu jednej jaskyne"
    if tokens and tokens <= GENERIC_CAVE_CARD_TOKENS:
        return "generická karta bez jednoznačného názvu jaskyne"
    if any(token in context or token in name_key for token in FOREIGN_CONTEXT_TOKENS) and not any(
        token in context for token in SLOVAK_CONTEXT_TOKENS
    ):
        return "zahraničná alebo mimo-slovenská lokalita bez SMOPaJ záznamu"
    return ""


def shortlist_smopaj_candidates(
    cave: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    max_candidates: int = 12,
) -> list[dict[str, Any]]:
    context = cave_summary_context(cave)
    cave_name = str(cave.get("name") or "")
    cave_tokens = set(name_tokens(cave_name))
    if not cave_tokens:
        return []
    rows: list[dict[str, Any]] = []
    for entry in entries:
        entry_tokens = entry_name_token_set(entry)
        if entry_tokens and not (cave_tokens & entry_tokens):
            continue
        similarity = name_similarity(cave_name, entry)
        if similarity < 0.58:
            continue
        region_score = context_region_score(context, entry)
        combined = similarity + min(region_score, 4.0) * 0.12
        row = {
            "cave_number": str(entry.get("cave_number") or ""),
            "registry_number": str(entry.get("registry_number") or ""),
            "official_name": str(entry.get("official_name") or ""),
            "names": entry_names(entry),
            "geomorph_celok": str(entry.get("geomorph_celok") or ""),
            "geomorph_podcelok": str(entry.get("geomorph_podcelok") or ""),
            "geomorph_cast": str(entry.get("geomorph_cast") or ""),
            "name_score": round(similarity, 4),
            "context_score": round(region_score, 4),
            "score": round(combined, 4),
        }
        rows.append(row)
    return sorted(rows, key=lambda item: (-item["score"], -item["context_score"], item["official_name"]))[:max_candidates]


def heuristic_decision(cave: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    reject_reason = cave_is_probably_foreign_or_generic(cave)
    if not candidates:
        return {
            "decision": "defer",
            "cave_number": "",
            "confidence": 0.0,
            "reason": reject_reason or "bez dostatočne podobného kandidáta v SMOPaJ registri",
        }
    if reject_reason.startswith("generická"):
        return {
            "decision": "defer",
            "cave_number": "",
            "confidence": 0.0,
            "reason": reject_reason,
        }
    if reject_reason and candidates[0]["score"] < 0.88:
        return {
            "decision": "defer",
            "cave_number": "",
            "confidence": 0.0,
            "reason": reject_reason,
        }
    top = candidates[0]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
    margin = top["score"] - second_score
    if top["name_score"] >= 0.96 and (top["context_score"] > 0 or margin >= 0.16 or len(candidates) == 1):
        confidence = min(0.94, 0.78 + margin + min(float(top["context_score"]), 2.0) * 0.04)
        return {
            "decision": "match",
            "cave_number": top["cave_number"],
            "confidence": round(confidence, 3),
            "reason": "jednoznačná názvová zhoda a kontext neodporuje kandidátovi",
        }
    if top["score"] >= 0.92 and margin >= 0.1 and top["context_score"] > 0:
        confidence = min(0.92, 0.76 + margin + min(float(top["context_score"]), 3.0) * 0.04)
        return {
            "decision": "match",
            "cave_number": top["cave_number"],
            "confidence": round(confidence, 3),
            "reason": "najlepší kandidát má podporu v názve aj geomorfologickom kontexte",
        }
    return {
        "decision": "defer",
        "cave_number": "",
        "confidence": 0.0,
        "reason": "nejednoznačná zhoda: viac kandidátov je príliš podobných alebo chýba lokálny kontext",
    }


def ai_prompt(cave: dict[str, Any], candidates: list[dict[str, Any]], context: str) -> str:
    candidate_lines = []
    for item in candidates:
        candidate_lines.append(
            json.dumps(
                {
                    "cave_number": item["cave_number"],
                    "official_name": item["official_name"],
                    "names": item["names"][:8],
                    "geomorphology": " / ".join(
                        part
                        for part in [item["geomorph_celok"], item["geomorph_podcelok"], item["geomorph_cast"]]
                        if part
                    ),
                    "registry_number": item["registry_number"],
                    "name_score": item["name_score"],
                    "context_score": item["context_score"],
                },
                ensure_ascii=False,
            )
        )
    return (
        "Si odborný slovenský speleologický bibliograf. "
        "Máš priradiť bibliografickú kartu jaskyne k oficiálnemu SMOPaJ registru jaskýň SR. "
        "Vyber kandidáta iba vtedy, keď názov, pádové varianty a kontext článkov ukazujú na tú istú jaskyňu. "
        "Ak ide o zahraničnú lokalitu, generickú frázu, viac rôznych jaskýň s rovnakým názvom alebo chýba lokálny dôkaz, zvoľ defer. "
        "Nevymýšľaj nové čísla; cave_number musí byť prázdny alebo jedno z kandidátnych čísel. "
        "Vráť iba JSON podľa schémy: decision, cave_number, confidence, reason.\n\n"
        f"Karta:\n{json.dumps({'name': cave.get('name'), 'slug': cave.get('slug'), 'aliases': cave.get('aliases'), 'area': cave.get('area')}, ensure_ascii=False)}\n\n"
        "Kontext článkov:\n"
        f"{context}\n\n"
        "Kandidáti SMOPaJ:\n"
        + "\n".join(candidate_lines)
    )


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def run_ollama_decision(
    cave: dict[str, Any],
    candidates: list[dict[str, Any]],
    context: str,
    *,
    model: str,
    timeout: int,
) -> dict[str, Any]:
    response = requests.post(
        OLLAMA_GENERATE_URL,
        json={
            "model": model,
            "prompt": ai_prompt(cave, candidates, context),
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0.0,
                "top_p": 0.8,
                "num_predict": 260,
            },
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Ollama API {response.status_code}: {response.text[:500]}")
    payload = response.json()
    return extract_json_object(payload.get("response") or "")


def run_codex_decision(
    cave: dict[str, Any],
    candidates: list[dict[str, Any]],
    context: str,
    *,
    model: str,
    timeout: int,
) -> dict[str, Any]:
    return run_codex_json(ai_prompt(cave, candidates, context), AI_DECISION_SCHEMA, model, timeout)


def validate_decision(decision: dict[str, Any], candidates: list[dict[str, Any]], min_confidence: float) -> dict[str, Any]:
    candidate_numbers = {str(item["cave_number"]) for item in candidates}
    normalized = {
        "decision": str(decision.get("decision") or "defer").strip().lower(),
        "cave_number": str(decision.get("cave_number") or "").strip(),
        "confidence": float(decision.get("confidence") or 0.0),
        "reason": str(decision.get("reason") or "").strip(),
    }
    if normalized["decision"] != "match":
        normalized["decision"] = "defer"
        normalized["cave_number"] = ""
        return normalized
    if normalized["cave_number"] not in candidate_numbers or normalized["confidence"] < min_confidence:
        normalized["decision"] = "defer"
        normalized["cave_number"] = ""
    return normalized


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_fulltext_subset(path: Path, article_ids: set[int]) -> dict[int, str]:
    if not article_ids or not path.exists():
        return {}
    result: dict[int, str] = {}
    for record in iter_jsonl(path) or []:
        article_id = int(record.get("id") or 0)
        if article_id in article_ids:
            result[article_id] = str(record.get("text") or "")
            if len(result) == len(article_ids):
                break
    return result


def should_process_cave(cave: dict[str, Any], slug_filter: set[str], min_articles: int) -> bool:
    if cave.get("smopaj_cave_number"):
        return False
    if slug_filter and str(cave.get("slug") or "") not in slug_filter:
        return False
    if int(cave.get("article_count") or 0) < min_articles:
        return False
    return True


def decision_to_match(
    cave: dict[str, Any],
    decision: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    backend: str,
    model: str,
) -> dict[str, Any]:
    selected = next(item for item in candidates if item["cave_number"] == decision["cave_number"])
    match = {
        "cave_slug": cave["slug"],
        "cave_name": cave["name"],
        "cave_number": decision["cave_number"],
        "confidence": "ai-assisted-high" if decision["confidence"] >= 0.86 else "ai-assisted-medium",
        "match_source": "ai-generated-override",
        "note": (
            f"{backend}/{model}: {decision['reason']} "
            f"Vybraný kandidát: {selected['official_name']} "
            f"({selected['geomorph_celok']} / {selected['geomorph_podcelok']} / {selected['geomorph_cast']})."
        ),
    }
    if cave.get("area"):
        match["cave_area"] = cave["area"]
    return {key: value for key, value in match.items() if str(value or "").strip()}


def process_caves(args: argparse.Namespace) -> dict[str, Any]:
    caves = load_json(args.caves, [])
    register = load_json(args.register, {})
    entries = [entry for entry in register.get("entries", []) if isinstance(entry, dict)]
    existing_output = load_json(args.output, {}) if args.resume and args.output.exists() and not args.dry_run else {}
    processed_slugs = {
        str(item.get("cave_slug") or "")
        for item in [*(existing_output.get("matches") or []), *(existing_output.get("deferred") or [])]
        if str(item.get("cave_slug") or "")
    }
    selected_caves = [
        cave
        for cave in caves
        if isinstance(cave, dict)
        and should_process_cave(cave, set(args.slug or []), args.min_articles)
        and str(cave.get("slug") or "") not in processed_slugs
    ]
    selected_caves.sort(key=lambda item: (-int(item.get("article_count") or 0), str(item.get("name") or "")))
    if args.limit:
        selected_caves = selected_caves[: args.limit]

    article_ids = {
        int(article.get("id") or 0)
        for cave in selected_caves
        for article in cave.get("articles") or []
        if int(article.get("id") or 0)
    }
    fulltext_by_id = load_fulltext_subset(args.fulltext, article_ids) if args.fulltext_context else {}

    output = {
        "schema_version": "smopaj-cave-ai-matches/v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "backend": args.backend,
        "model": args.codex_model if args.backend == "codex" else args.model,
        "ollama_model": args.model,
        "codex_model": args.codex_model,
        "min_confidence": args.min_confidence,
        "sources": [
            {
                "title": "AI-assisted SMOPaJ cave register matching",
                "date": dt.date.today().isoformat(),
                "note": "Generated suggestions; manually curated overrides still take precedence.",
            }
        ],
        "matches": list(existing_output.get("matches") or []),
        "deferred": list(existing_output.get("deferred") or []),
        "stats": {
            "selected": len(selected_caves),
            "matched": len(existing_output.get("matches") or []),
            "deferred": len(existing_output.get("deferred") or []),
            "errors": 0,
            "resumed_matches": len(existing_output.get("matches") or []),
            "resumed_deferred": len(existing_output.get("deferred") or []),
        },
    }

    for index, cave in enumerate(selected_caves, start=1):
        started = time.monotonic()
        candidates = shortlist_smopaj_candidates(cave, entries, max_candidates=args.max_candidates)
        context = cave_summary_context(cave, fulltext_by_id)
        decision = heuristic_decision(cave, candidates)
        backend_used = "heuristic"
        error = ""

        if candidates and args.backend in {"ollama", "codex", "auto"}:
            try:
                if args.backend in {"ollama", "auto"}:
                    decision = run_ollama_decision(cave, candidates, context, model=args.model, timeout=args.timeout)
                    backend_used = "ollama"
                else:
                    decision = run_codex_decision(cave, candidates, context, model=args.codex_model, timeout=args.timeout)
                    backend_used = "codex"
            except Exception as exc:
                error = str(exc)
                if args.backend == "auto" and args.codex_fallback:
                    try:
                        decision = run_codex_decision(cave, candidates, context, model=args.codex_model, timeout=args.timeout)
                        backend_used = "codex"
                        error = ""
                    except (CodexBackendError, Exception) as codex_exc:
                        error = f"{error}; codex fallback: {codex_exc}"
                if error:
                    output["stats"]["errors"] += 1
                    decision = {
                        "decision": "defer",
                        "cave_number": "",
                        "confidence": 0.0,
                        "reason": f"AI backend error: {error[:500]}",
                    }

        decision = validate_decision(decision, candidates, args.min_confidence)
        if decision["decision"] == "match":
            output["matches"].append(
                decision_to_match(cave, decision, candidates, backend=backend_used, model=args.model if backend_used != "codex" else args.codex_model)
            )
            output["stats"]["matched"] += 1
            status = "match"
        else:
            output["deferred"].append(
                {
                    "cave_slug": cave.get("slug", ""),
                    "cave_name": cave.get("name", ""),
                    "reason": decision.get("reason") or error or "AI nevybrala dostatočne istý SMOPaJ záznam",
                    "candidate_numbers": [item["cave_number"] for item in candidates[:5]],
                }
            )
            output["stats"]["deferred"] += 1
            status = "defer"

        print(
            f"[{index}/{len(selected_caves)}] {status} {cave.get('name')} "
            f"candidates={len(candidates)} backend={backend_used} time={time.monotonic() - started:.1f}s",
            flush=True,
        )
        if not args.dry_run:
            write_json(args.output, output)

    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caves", type=Path, default=DEFAULT_CAVES_PATH)
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER_PATH)
    parser.add_argument("--fulltext", type=Path, default=DEFAULT_FULLTEXT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--backend", choices=["heuristic", "ollama", "codex", "auto"], default="heuristic")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--codex-model", default="gpt-5.5")
    parser.add_argument("--codex-fallback", action="store_true")
    parser.add_argument("--fulltext-context", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-articles", type=int, default=1)
    parser.add_argument("--max-candidates", type=int, default=12)
    parser.add_argument("--min-confidence", type=float, default=0.82)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--slug", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = process_caves(args)
    if not args.dry_run:
        write_json(args.output, output)
    print(json.dumps(output["stats"], ensure_ascii=False, indent=2))
    if args.dry_run:
        print(f"dry-run output path would be: {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
