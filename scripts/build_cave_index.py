#!/usr/bin/env python3
"""Build a compact cave/lokalita index for static web timeline pages."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "web" / "src" / "data" / "caves.json"
DEFAULT_ALIASES_PATH = BASE_DIR / "data" / "cave_aliases.json"
DEFAULT_GEOMORPHOLOGY_PATH = BASE_DIR / "data" / "geomorphology_regions.json"
DEFAULT_SMOPAJ_REGISTER_PATH = BASE_DIR / "data" / "smopaj_cave_register_2017.json"
DEFAULT_SMOPAJ_OVERRIDES_PATH = BASE_DIR / "data" / "smopaj_cave_match_overrides.json"
DEFAULT_SMOPAJ_AI_MATCHES_PATH = BASE_DIR / "data" / "smopaj_cave_ai_matches.json"
PDF_LINK_PAGE_OFFSET = 2
DEFAULT_JOURNAL_ID = "spravodaj_sss"
DEFAULT_JOURNAL_TITLE = "Spravodaj Slovenskej speleologickej spoločnosti"
DEFAULT_JOURNAL_SHORT_TITLE = "Spravodaj SSS"
CAVE_HEADWORDS = (
    "jaskyňa",
    "jaskyne",
    "jaskyni",
    "jaskyňu",
    "jaskyňou",
    "jeskyňa",
    "jeskyně",
    "priepasť",
    "priepasti",
    "priepasťou",
    "diera",
    "diery",
    "dieru",
    "ľadnica",
    "jama",
    "sifón",
    "vyvieračka",
)
CAVE_HEADWORD_PATTERN = "|".join(re.escape(word) for word in CAVE_HEADWORDS)
CAVE_NAME_CHAR_PATTERN = r"A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž0-9'’\-/"
CAVE_GENERIC_PREFIXES = {
    "ake",
    "administrativna",
    "analyza",
    "ako",
    "autor",
    "bezvyznamne",
    "boli",
    "charakter",
    "charakteristika",
    "chybne",
    "clenovia",
    "dalsia",
    "dalsi",
    "dalsie",
    "decembrovej",
    "desatoro",
    "dobrodruzstvo",
    "dodatok",
    "dojmy",
    "dokopy",
    "domeranie",
    "doplnenie",
    "druhy",
    "dvadsat",
    "dve",
    "elektraren",
    "exkurzia",
    "expedicia",
    "historia",
    "informacia",
    "instalacia",
    "k",
    "kratko",
    "medzinarodny",
    "mylna",
    "najdlhsie",
    "naj",
    "najdeme",
    "najfarebnejsie",
    "najhlbsie",
    "najnavstevovanejsie",
    "najvacsie",
    "nakreslite",
    "naucny",
    "navrh",
    "navsteva",
    "navstevnost",
    "nove",
    "novych",
    "o",
    "ochrana",
    "objavili",
    "osvetlenie",
    "oneskoreny",
    "opat",
    "oprava",
    "podmienky",
    "pokracovanie",
    "podorysna",
    "popisovanie",
    "poznamky",
    "prehlad",
    "premia",
    "pribeh",
    "program",
    "prva",
    "prispevok",
    "prieskum",
    "rekonstrukcia",
    "sprava",
    "speleologicky",
    "spristupnene",
    "spresnenie",
    "strucna",
    "strucne",
    "strucny",
    "technicke",
    "text",
    "the",
    "udaje",
    "sucastou",
    "vyhlasenie",
    "vyhodnotenie",
    "vplyv",
    "vsetkym",
    "vyskum",
    "vyskumna",
    "vysledky",
    "zameranie",
    "zameriavanie",
    "zaklady",
    "zasady",
    "vystrojovanie",
}
CAVE_GENERIC_WORDS = {
    "akcii",
    "a",
    "alebo",
    "ako",
    "akcia",
    "akcie",
    "administrativna",
    "bezpecnost",
    "ciny",
    "clanok",
    "co",
    "cesta",
    "cerpanie",
    "ceskoslovenske",
    "cesky",
    "cerpacie",
    "cerpaci",
    "cistenie",
    "dokumentacia",
    "do",
    "gajda",
    "gajdu",
    "geoparku",
    "jej",
    "koncoveho",
    "ladovej",
    "jaskyniar",
    "jaskyniari",
    "jaskyniarska",
    "jaskyniarske",
    "jaskyniarsky",
    "jaskyniarstva",
    "jaskyniarstve",
    "jaskyniarstvo",
    "lokality",
    "mapovanie",
    "mapa",
    "meranie",
    "mikroklima",
    "nazov",
    "navstevnost",
    "ochrana",
    "opis",
    "pomocky",
    "pokus",
    "pokusy",
    "prehlad",
    "pre",
    "prispevok",
    "prirody",
    "rok",
    "roky",
    "sa",
    "sifon",
    "skolenie",
    "skryva",
    "slovenska",
    "slovenske",
    "slovenskeho",
    "slovenskych",
    "spomienky",
    "sprava",
    "spravy",
    "spristupnene",
    "straze",
    "sutaze",
    "sveta",
    "tabulka",
    "text",
    "tyzden",
    "tyzdna",
    "vyskresov",
    "vyskum",
    "vyskumna",
    "vyhlasenie",
    "vyhodnotenie",
    "vyznamne",
    "vystrojovanie",
    "zameranie",
    "zameriavanie",
    "zmienky",
    "uraz",
    "zahada",
    "zachranny",
    "zachrana",
    "zapis",
    "zber",
    "ziadna",
    "zname",
    "zostup",
    "kosti",
}
CAVE_GENERIC_EXACT_NAMES = {
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
    "poloha jaskyne",
    "prakticka starostlivost o jaskyne",
    "mylna informacia dalekopisu o objave jaskyne",
    "nakreslite si jaskynu",
    "gajdu o jaskyne",
    "jaskyna slovenskeho krasu",
    "kratka riecna jaskyna",
    "novohradskeho geoparku budu aj jaskyne",
    "priepastovita jaskyna",
    "navsteva spristupnenej jaskyne",
    "objavili nam novu jaskynu",
    "oneskoreny pribeh objavu jaskyne",
    "oprava uzaveru jaskyne",
    "program axonometrickeho znazornenia jaskyne",
    "rekonstrukcia uzaveru jaskyne zla diera",
    "rudolf gajda",
    "starostlivost o jaskyne",
    "strucne o jaskyni",
    "strucne o priepasti",
    "strucne o prieskume jaskyne",
    "sucastou novohradskeho geoparku budu aj jaskyne",
    "vystrojovanie jaskyne",
    "vyuzitie jaskyne",
    "znovuotvorenie jaskyne",
}
CAVE_AREA_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Slovenský raj / Psie diery",
        (
            r"\bpsie diery\b",
            r"\bpsich dier\b",
            r"\bmedvedej chodby\b",
        ),
    ),
    (
        "Slovenský raj / Stratenská hornatina",
        (
            r"\bslovensky raj\b",
            r"\bslovenskom raji\b",
            r"\bstratensk\w* hornatin\w*\b",
            r"\bglack\w* planin\w*\b",
            r"\bplanin\w* glac\b",
            r"\bmasiv\w* glatz\b",
            r"\bglatz\b",
            r"\bglac\b",
        ),
    ),
    (
        "Demänovská dolina / Nízke Tatry",
        (
            r"\bdemanovsk\w* dolin\w*\b",
            r"\bdemanovsk\w+ medved\w+ jaskyn\w*\b",
            r"\bdemanovsk\w+ jaskyn\w*\b",
        ),
    ),
    (
        "Jánska dolina / Nízke Tatry",
        (
            r"\bjansk\w* dolin\w*\b",
            r"\bnizk\w* tatr\w*\b",
            r"\bjaskyn\w* zlomisk\b",
            r"\bzlomisk\b",
            r"\bliptovsky jan\b",
        ),
    ),
    (
        "Vrátna dolina / Malá Fatra",
        (
            r"\bvratn\w* dolin\w*\b",
            r"\bmedved\w+ jaskyn\w* ii\b",
            r"\bwratnuella\b",
            r"\bpod suchym\b",
            r"\bjaskyniarsk\w* klub\w* varin\b",
            r"\bklub\w* varin\b",
            r"\bvarin\b",
        ),
    ),
    (
        "Malá Fatra",
        (
            r"\bmala fatra\b",
            r"\bmalej fatre\b",
        ),
    ),
    (
        "Belianska dolina / Veľká Fatra",
        (
            r"\bbeliansk\w* dolin\w*\b",
            r"\bvelk\w* fatr\w*\b",
            r"\bjavorin\w*\b",
            r"\bblatnic\w*\b",
        ),
    ),
    (
        "Nitrické vrchy",
        (
            r"\bnitrick\w* vrch\w*\b",
            r"\bvestenic\w*\b",
            r"\bhradistnic\w*\b",
            r"\brokos\w*\b",
        ),
    ),
    (
        "Tuhársky kras / Revúcka vrchovina",
        (
            r"\btuharsk\w* kras\w*\b",
            r"\brevuck\w* vrchovin\w*\b",
            r"\bmara medved\w*\b",
        ),
    ),
    (
        "Humenec / Čierna Hora",
        (
            r"\bhumen\w*\b",
            r"\bcierna hora\b",
            r"\bciernej hore\b",
        ),
    ),
    (
        "Poľsko",
        (
            r"\bpolsk\w*\b",
            r"\bkletn\w*\b",
            r"\bkralick\w* sneznik\w*\b",
        ),
    ),
)
AREA_SPLIT_CAVE_NAMES = {
    "medvedia-jaskyna",
    "medvedie-jaskyne",
}
AREA_TAG_CAVE_NAMES = {
    "jaskyna-psie-diery",
}
CAVE_AREA_OVERRIDES: dict[tuple[int, str], str] = {
    (1361, "medvedia-jaskyna"): "Jánska dolina / Nízke Tatry",
    (5686, "medvedia-jaskyna"): "Slovenský raj / Stratenská hornatina",
    (5658, "medvedia-jaskyna"): "Slovenský raj / Stratenská hornatina",
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


CAVE_HEADWORD_KEYS = {normalize_text(word) for word in CAVE_HEADWORDS}
REGISTERED_MATCH_SKIP_TOKENS = CAVE_HEADWORD_KEYS | {
    "a",
    "alebo",
    "cave",
    "do",
    "na",
    "nad",
    "pod",
    "pre",
    "pri",
    "the",
    "v",
    "vo",
    "z",
    "zo",
}


def slugify(value: Any) -> str:
    return normalize_text(value).replace(" ", "-") or "jaskyna"


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        key = slugify(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def clean_inferred_cave_name(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^[,;:–—\-\s]+|[,;:–—\-\s]+$", "", text)
    text = re.sub(r"\s+(?:v|vo|na|pri|pod|nad|z|zo|do|pre|a|alebo)$", "", text, flags=re.IGNORECASE)
    words = text.split()
    for index, word in enumerate(words):
        if index > 0 and normalize_text(word) in {"a", "alebo", "do", "na", "nad", "pod", "pre", "pri", "v", "vo", "z", "zo"}:
            text = " ".join(words[:index])
            break
    return text.strip()


def article_context_text(article: dict[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in (
            article.get("title"),
            article.get("abstract"),
            article.get("journal_title"),
            article.get("journal_short_title"),
        )
    )


def is_contextual_cave_candidate(value: Any) -> bool:
    tokens = normalize_text(value).split()
    if not tokens:
        return False
    return tokens[0] in {
        "charakter",
        "dovody",
        "komplexny",
        "moznosti",
        "niekolkorocne",
        "objav",
        "podrobny",
        "prejavy",
        "revizne",
        "spodnej",
        "uzavretie",
        "vek",
        "vyskum",
    }


def normalize_cave_candidate_name(cave_name: str, article: dict[str, Any]) -> str:
    text = re.sub(r"\s+", " ", str(cave_name or "")).strip()
    candidate_key = normalize_text(text)
    if candidate_key.startswith("jaskyn") and candidate_key.endswith(" cave"):
        text = re.sub(r"\s+cave\s*$", "", text, flags=re.IGNORECASE).strip()
        cave_name = text
        candidate_key = normalize_text(text)
    candidate_key = normalize_text(cave_name)
    context_key = normalize_text(f"{cave_name} {article_context_text(article)}")

    if "psie diery" in context_key and ("medvedej chodby" in context_key or candidate_key.startswith("medvedej chodby")):
        return "Jaskyňa Psie diery"
    if "mara medved" in context_key:
        return "Jaskyňa Mara medvedia"
    if "vestenic" in context_key and "medved" in context_key and "jaskyn" in context_key:
        return "Vestenická Medvedia jaskyňa"
    if "demanov" in context_key and "medved" in context_key and "jaskyn" in context_key:
        return "Demänovská medvedia jaskyňa"
    if re.search(r"\bmedvedie jaskyne\b", candidate_key):
        return "Medvedie jaskyne"
    if "medved" in candidate_key and "jaskyn" in candidate_key:
        if re.search(r"\b(?:jaskyn\w* +medved\w*|medved\w* +jaskyn\w*) +(ii|2)\b", context_key):
            return "Jaskyňa Medvedia II"
        if "medvedej jaskyn" in candidate_key or "medvedia jaskyn" in candidate_key or is_contextual_cave_candidate(cave_name):
            return "Medvedia jaskyňa"
    return cave_name


def infer_cave_area(article: dict[str, Any], cave_name: str) -> str:
    article_id = int(article.get("id") or 0)
    override = CAVE_AREA_OVERRIDES.get((article_id, slugify(cave_name)))
    if override:
        return override

    context_key = normalize_text(article_context_text(article))
    for area, patterns in CAVE_AREA_RULES:
        if any(re.search(pattern, context_key) for pattern in patterns):
            return area
    return ""


def should_keep_cave_area(name_key: str) -> bool:
    return "medved" in name_key or name_key in AREA_SPLIT_CAVE_NAMES or name_key in AREA_TAG_CAVE_NAMES


def is_probable_cave_name(value: str) -> bool:
    text = clean_inferred_cave_name(value)
    if len(text) < 4 or len(text) > 86:
        return False
    normalized = normalize_text(text)
    if not normalized:
        return False
    if normalized in CAVE_GENERIC_EXACT_NAMES:
        return False
    tokens = normalized.split()
    if len(tokens) == 1 and tokens[0].isdigit():
        return False
    if tokens and tokens[0].isdigit():
        return False
    if len(tokens) > 7:
        return False
    if tokens[0] in CAVE_GENERIC_PREFIXES:
        return False
    if any(token in CAVE_GENERIC_WORDS for token in tokens):
        return False
    if re.search(r"\bnaj(?:dlh|hlb)", normalized):
        return False
    if len(tokens) == 1 and tokens[0] in CAVE_GENERIC_WORDS:
        return False
    generic_hits = sum(1 for token in tokens if token in CAVE_GENERIC_WORDS)
    if generic_hits >= max(2, len(tokens) // 2):
        return False
    if re.search(r"\b(?:sss|uis|msk|rok|roky|storoč|vyroc|tyzden|tabulka)\b", normalized):
        return False
    return True


def infer_caves_from_text(text: str) -> list[str]:
    if not text:
        return []

    inferred: list[str] = []
    type_before = re.compile(
        rf"(?=\b(?P<head>(?i:{CAVE_HEADWORD_PATTERN}))\s+"
        rf"(?P<name>[A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ0-9][{CAVE_NAME_CHAR_PATTERN}]+"
        rf"(?:\s+(?:[a-záäčďéíĺľňóôŕšťúýž]+|[A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ0-9][{CAVE_NAME_CHAR_PATTERN}]+)){{0,5}}))",
    )
    name_before = re.compile(
        rf"\b(?P<name>[A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ0-9][{CAVE_NAME_CHAR_PATTERN}]+"
        rf"(?:\s+(?:[a-záäčďéíĺľňóôŕšťúýž]+|[A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ0-9][{CAVE_NAME_CHAR_PATTERN}]+)){{0,4}})"
        rf"\s+(?P<head>(?i:{CAVE_HEADWORD_PATTERN}))\b",
    )

    for match in type_before.finditer(text):
        head = match.group("head")
        name = clean_inferred_cave_name(match.group("name"))
        if not is_probable_cave_name(name):
            continue
        normalized_head = normalize_text(head)
        if normalized_head.startswith("jaskyn") or normalized_head.startswith("jeskyn"):
            candidate = name if normalize_text(name).startswith(("jaskyn", "jeskyn")) else f"Jaskyňa {name}"
        elif normalized_head.startswith("priepast"):
            candidate = name if "priepast" in normalize_text(name) else f"Priepasť {name}"
        else:
            candidate = name
        if is_probable_cave_name(candidate):
            inferred.append(candidate)

    for match in name_before.finditer(text):
        left_name = match.group("name")
        left_tokens = normalize_text(left_name).split()
        if any(token in {"v", "vo", "z", "zo", "do", "na", "pri", "pod", "nad"} for token in left_tokens):
            continue
        candidate = clean_inferred_cave_name(f"{match.group('name')} {match.group('head')}")
        if is_probable_cave_name(candidate):
            inferred.append(candidate)

    return unique_strings(inferred)


def infer_special_caves_from_article(article: dict[str, Any]) -> list[str]:
    context_key = normalize_text(article_context_text(article))
    candidates: list[str] = []
    if re.search(r"\bmedved(?:ia|ej|iu|ou|ie|ich|im|i)? +jaskyn", context_key):
        candidate = normalize_cave_candidate_name("Medvedia jaskyňa", article)
        if infer_cave_area(article, candidate):
            candidates.append(candidate)
    return unique_strings(candidates)


def article_cave_candidates(
    article: dict[str, Any],
    registered_matchers: dict[str, list[dict[str, Any]]] | None = None,
) -> list[str]:
    knowledge = article.get("knowledge") or {}
    explicit = (
        list(article.get("caves") or [])
        + list(knowledge.get("caves") or [])
        + list(knowledge.get("locations") or [])
    )
    explicit = [name for name in unique_strings(explicit) if is_probable_cave_name(name)]
    registered = infer_registered_caves_from_article(article, registered_matchers or {})
    if registered and not article.get("caves_verified"):
        special = infer_special_caves_from_article(article)
        return unique_strings([*registered, *special])
    if explicit:
        return explicit
    inferred = infer_caves_from_text(". ".join([article.get("title") or "", article.get("abstract") or ""]))
    if not inferred:
        inferred = infer_special_caves_from_article(article)
    return unique_strings(inferred)


def load_cave_aliases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    aliases = data.get("aliases", []) if isinstance(data, dict) else data
    if not isinstance(aliases, list):
        raise ValueError(f"Invalid cave alias file: {path}")
    return aliases


def load_geomorphology(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid geomorphology file: {path}")
    return data


def load_smopaj_cave_register(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid SMOPaJ cave register file: {path}")
    return data


def load_smopaj_cave_match_overrides(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid SMOPaJ cave match override file: {path}")
    matches = data.get("matches", [])
    if matches is not None and not isinstance(matches, list):
        raise ValueError(f"Invalid SMOPaJ cave match override file: {path}")
    article_matches = data.get("article_matches", [])
    if article_matches is not None and not isinstance(article_matches, list):
        raise ValueError(f"Invalid SMOPaJ cave match override file: {path}")
    return data


def smopaj_match_article_ids(match: dict[str, Any]) -> list[int]:
    raw_ids: list[Any] = []
    if match.get("article_id") not in (None, ""):
        raw_ids.append(match.get("article_id"))
    raw_ids.extend(match.get("article_ids") or [])

    article_ids: list[int] = []
    for raw_id in raw_ids:
        try:
            article_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if article_id > 0 and article_id not in article_ids:
            article_ids.append(article_id)
    return article_ids


def smopaj_match_identity_keys(match: dict[str, Any]) -> list[str]:
    key_values: list[str] = []
    cave_slug = str(match.get("cave_slug") or "").strip()
    cave_name = str(match.get("cave_name") or "").strip()
    cave_area = str(match.get("cave_area") or match.get("area") or "").strip()
    if cave_slug:
        key_values.extend(smopaj_override_lookup_keys(cave_slug, cave_area))
    if cave_name:
        key_values.extend(smopaj_override_lookup_keys(cave_name, cave_area))
    return sorted({key for key in key_values if key})


def merge_smopaj_match_sources(*sources: dict[str, Any] | None) -> dict[str, Any]:
    """Merge curated and generated SMOPaJ match files.

    Earlier sources win. The first source is treated as manually curated;
    later sources are treated as generated suggestions unless they specify
    their own `match_source`.
    """
    merged: dict[str, Any] = {
        "schema_version": "smopaj-cave-match-overrides/v1",
        "sources": [],
        "matches": [],
        "article_matches": [],
        "deferred": [],
    }
    seen_keys: set[str] = set()
    seen_article_keys: set[tuple[int, str]] = set()

    for index, source in enumerate(sources):
        if not isinstance(source, dict) or not source:
            continue
        source_label = "curated-override" if index == 0 else "ai-generated-override"
        merged["sources"].extend(source.get("sources") or [])
        merged["deferred"].extend(source.get("deferred") or [])
        matches = source.get("matches", [])
        if not isinstance(matches, list):
            raise ValueError("Invalid SMOPaJ cave match source: matches must be a list")
        for match in matches:
            if not isinstance(match, dict):
                raise ValueError("Invalid SMOPaJ cave match source entry")
            identity_keys = smopaj_match_identity_keys(match)
            if not identity_keys:
                raise ValueError("Invalid SMOPaJ cave match source entry without cave_slug or cave_name")
            if any(key in seen_keys for key in identity_keys):
                continue
            normalized_match = dict(match)
            normalized_match.setdefault("match_source", source_label)
            merged["matches"].append(normalized_match)
            seen_keys.update(identity_keys)

        article_matches = source.get("article_matches", [])
        if not isinstance(article_matches, list):
            raise ValueError("Invalid SMOPaJ cave match source: article_matches must be a list")
        for match in article_matches:
            if not isinstance(match, dict):
                raise ValueError("Invalid SMOPaJ cave article match source entry")
            identity_keys = smopaj_match_identity_keys(match)
            article_ids = smopaj_match_article_ids(match)
            if not identity_keys:
                raise ValueError("Invalid SMOPaJ cave article match source entry without cave_slug or cave_name")
            if not article_ids:
                raise ValueError("Invalid SMOPaJ cave article match source entry without article_ids")
            article_identity_keys = {(article_id, key) for article_id in article_ids for key in identity_keys}
            if any(key in seen_article_keys for key in article_identity_keys):
                continue
            normalized_match = dict(match)
            normalized_match["article_ids"] = article_ids
            normalized_match.setdefault("match_source", source_label)
            merged["article_matches"].append(normalized_match)
            seen_article_keys.update(article_identity_keys)

    return merged


def build_alias_lookup(entries: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for entry in entries:
        canonical = str(entry.get("canonical") or "").strip()
        if not canonical:
            continue
        names = [canonical, *list(entry.get("aliases") or [])]
        for name in unique_strings(names):
            lookup[slugify(name)] = canonical
            lookup[normalize_text(name)] = canonical
    return lookup


def cave_match_keys(value: Any) -> list[str]:
    normalized = normalize_text(value)
    if not normalized:
        return []
    keys = [normalized]
    tokens = normalized.split()
    if len(tokens) > 1 and tokens[0] in {normalize_text(word) for word in CAVE_HEADWORDS}:
        keys.append(" ".join(tokens[1:]))
    return unique_strings(keys)


def build_smopaj_lookup(data: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    entries = data.get("entries", []) if isinstance(data, dict) else []
    if not isinstance(entries, list):
        return buckets
    for entry in entries:
        if not isinstance(entry, dict) or not str(entry.get("cave_number") or "").strip():
            continue
        names = unique_strings([entry.get("official_name", ""), *list(entry.get("names") or []), *list(entry.get("aliases") or [])])
        for name in names:
            for key in cave_match_keys(name):
                buckets[key].append(entry)
    return buckets


def build_smopaj_number_lookup(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    entries = data.get("entries", []) if isinstance(data, dict) else []
    if not isinstance(entries, list):
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cave_number = str(entry.get("cave_number") or "").strip()
        if cave_number and cave_number not in lookup:
            lookup[cave_number] = entry
    return lookup


def smopaj_override_base_keys(value: Any) -> list[str]:
    keys: list[str] = []
    for key in (slugify(value), normalize_text(value)):
        if key and key not in keys:
            keys.append(key)
    return keys


def smopaj_override_lookup_keys(value: Any, cave_area: str = "") -> list[str]:
    area_slug = slugify(cave_area) if cave_area else ""
    area_key = normalize_text(cave_area) if cave_area else ""
    keys: list[str] = []
    for base_key in smopaj_override_base_keys(value):
        if area_slug:
            keys.append(f"{base_key}--{area_slug}")
            keys.append(f"{base_key}::{area_key}")
        else:
            keys.append(base_key)
    return [key for key in keys if key]


def build_smopaj_override_lookup(
    overrides: dict[str, Any] | None,
    smopaj_register: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not overrides:
        return {}
    entries_by_number = build_smopaj_number_lookup(smopaj_register)
    lookup: dict[str, dict[str, Any]] = {}
    matches = overrides.get("matches", []) if isinstance(overrides, dict) else []
    if not isinstance(matches, list):
        raise ValueError("Invalid SMOPaJ cave match overrides: matches must be a list")

    for match in matches:
        if not isinstance(match, dict):
            raise ValueError("Invalid SMOPaJ cave match override entry")
        cave_number = str(match.get("cave_number") or "").strip()
        if not cave_number:
            raise ValueError("Invalid SMOPaJ cave match override entry without cave_number")
        entry = entries_by_number.get(cave_number)
        if not entry:
            raise ValueError(f"SMOPaJ cave match override references unknown cave_number: {cave_number}")

        key_values = smopaj_match_identity_keys(match)
        if not key_values:
            raise ValueError(f"SMOPaJ cave match override for {cave_number} has no cave_slug or cave_name")

        override = dict(match)
        override["entry"] = entry
        for key in {key for key in key_values if key}:
            existing = lookup.get(key)
            if existing and str(existing.get("cave_number") or "") != cave_number:
                raise ValueError(f"Conflicting SMOPaJ cave match override for key: {key}")
            lookup[key] = override
    return lookup


def build_smopaj_article_override_lookup(
    overrides: dict[str, Any] | None,
    smopaj_register: dict[str, Any] | None,
) -> dict[tuple[int, str], dict[str, Any]]:
    if not overrides:
        return {}
    entries_by_number = build_smopaj_number_lookup(smopaj_register)
    lookup: dict[tuple[int, str], dict[str, Any]] = {}
    matches = overrides.get("article_matches", []) if isinstance(overrides, dict) else []
    if not isinstance(matches, list):
        raise ValueError("Invalid SMOPaJ cave match overrides: article_matches must be a list")

    for match in matches:
        if not isinstance(match, dict):
            raise ValueError("Invalid SMOPaJ cave article match override entry")
        cave_number = str(match.get("cave_number") or "").strip()
        if not cave_number:
            raise ValueError("Invalid SMOPaJ cave article match override entry without cave_number")
        entry = entries_by_number.get(cave_number)
        if not entry:
            raise ValueError(f"SMOPaJ cave article match override references unknown cave_number: {cave_number}")

        article_ids = smopaj_match_article_ids(match)
        if not article_ids:
            raise ValueError(f"SMOPaJ cave article match override for {cave_number} has no article_ids")
        key_values = smopaj_match_identity_keys(match)
        if not key_values:
            raise ValueError(f"SMOPaJ cave article match override for {cave_number} has no cave_slug or cave_name")

        override = dict(match)
        override["article_ids"] = article_ids
        override["entry"] = entry
        for article_id in article_ids:
            for key in {key for key in key_values if key}:
                lookup_key = (article_id, key)
                existing = lookup.get(lookup_key)
                if existing and str(existing.get("cave_number") or "") != cave_number:
                    raise ValueError(f"Conflicting SMOPaJ cave article match override for article/key: {lookup_key}")
                lookup[lookup_key] = override
    return lookup


def resolve_smopaj_override(
    cave_names: list[str],
    lookup: dict[str, dict[str, Any]],
    cave_area: str = "",
) -> dict[str, Any] | None:
    for cave_name in unique_strings(cave_names):
        for key in [*smopaj_override_lookup_keys(cave_name, cave_area), *smopaj_override_lookup_keys(cave_name)]:
            override = lookup.get(key)
            if override:
                return override
    return None


def resolve_smopaj_article_override(
    article_id: int,
    cave_names: list[str],
    lookup: dict[tuple[int, str], dict[str, Any]],
) -> dict[str, Any] | None:
    if not article_id:
        return None
    for cave_name in unique_strings(cave_names):
        for key in smopaj_override_lookup_keys(cave_name):
            override = lookup.get((article_id, key))
            if override:
                return override
    return None


def resolve_smopaj_entry(cave_name: str, lookup: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    matches: dict[str, dict[str, Any]] = {}
    for key in cave_match_keys(cave_name):
        for entry in lookup.get(key, []):
            cave_number = str(entry.get("cave_number") or "").strip()
            if cave_number:
                matches[cave_number] = entry
    if len(matches) != 1:
        return None
    return next(iter(matches.values()))


def region_from_smopaj_entry(entry: dict[str, Any] | None) -> dict[str, str]:
    if not entry:
        return {}
    celok = str(entry.get("geomorph_celok") or "").strip()
    podcelok = str(entry.get("geomorph_podcelok") or "").strip()
    cast = str(entry.get("geomorph_cast") or "").strip()
    local_area = cast or podcelok or celok
    region = {
        "local_area": local_area,
        "geomorph_unit": celok,
        "geomorph_area": celok,
        "geomorph_subunit": podcelok,
        "geomorph_part": cast,
        "confidence": "official-smopaj-2017",
        "source": "smopaj-cave-register-2017",
    }
    return {key: value for key, value in region.items() if value}


def area_label_from_smopaj_entry(entry: dict[str, Any] | None) -> str:
    if not entry:
        return ""
    values = [
        str(entry.get("geomorph_celok") or "").strip(),
        str(entry.get("geomorph_podcelok") or "").strip(),
        str(entry.get("geomorph_cast") or "").strip(),
    ]
    return " / ".join(unique_strings([value for value in values if value]))


def unique_smopaj_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_number: dict[str, dict[str, Any]] = {}
    for entry in entries:
        cave_number = str(entry.get("cave_number") or "").strip()
        if cave_number:
            by_number[cave_number] = entry
    if len(by_number) != 1:
        return None
    return next(iter(by_number.values()))


def unique_smopaj_match(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_number: dict[str, dict[str, Any]] = {}
    for match in matches:
        entry = match.get("entry") if isinstance(match, dict) else None
        if not isinstance(entry, dict):
            continue
        cave_number = str(entry.get("cave_number") or "").strip()
        if not cave_number:
            continue
        current = by_number.get(cave_number)
        if current is None or (not current.get("override") and match.get("override")):
            by_number[cave_number] = match
    if len(by_number) != 1:
        return None
    return next(iter(by_number.values()))


def clean_region_entry(entry: Any) -> dict[str, str]:
    if not isinstance(entry, dict):
        return {}
    allowed_keys = (
        "local_area",
        "geomorph_unit",
        "geomorph_parent",
        "geomorph_subunit",
        "geomorph_part",
        "geomorph_area",
        "geomorph_subprovince",
        "confidence",
        "source",
    )
    return {key: str(entry.get(key) or "").strip() for key in allowed_keys if str(entry.get(key) or "").strip()}


def build_geomorphology_lookup(data: dict[str, Any] | None) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    area_lookup: dict[str, dict[str, str]] = {}
    cave_lookup: dict[str, dict[str, str]] = {}
    if not data:
        return area_lookup, cave_lookup

    for area_name, entry in (data.get("areas") or {}).items():
        region = clean_region_entry(entry)
        if region:
            area_lookup[normalize_text(area_name)] = region

    for cave_name, entry in (data.get("caves") or {}).items():
        region = clean_region_entry(entry)
        if region:
            cave_lookup[slugify(cave_name)] = region
            cave_lookup[normalize_text(cave_name)] = region
    return area_lookup, cave_lookup


def resolve_geomorphology(
    cave_name: str,
    cave_area: str,
    area_lookup: dict[str, dict[str, str]],
    cave_lookup: dict[str, dict[str, str]],
) -> dict[str, str]:
    if cave_area:
        region = area_lookup.get(normalize_text(cave_area))
        if region:
            return dict(region)
    region = cave_lookup.get(slugify(cave_name)) or cave_lookup.get(normalize_text(cave_name))
    return dict(region) if region else {}


def canonical_cave_name(cave_name: str, alias_lookup: dict[str, str]) -> str:
    return alias_lookup.get(slugify(cave_name)) or alias_lookup.get(normalize_text(cave_name)) or cave_name


def first_page(article: dict[str, Any]) -> int:
    value = article.get("pdf_page_start")
    if value in (None, ""):
        match = re.match(r"\s*(\d+)", str(article.get("pages") or ""))
        value = match.group(1) if match else 1
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def pdf_page_offset(article: dict[str, Any]) -> int:
    try:
        return int(article.get("pdf_page_offset", PDF_LINK_PAGE_OFFSET))
    except (TypeError, ValueError):
        return PDF_LINK_PAGE_OFFSET


def pdf_link(article: dict[str, Any]) -> str:
    url = str(article.get("pdf_url") or "").strip()
    if not url:
        return ""
    return f"{url}#page={first_page(article) + pdf_page_offset(article)}"


def has_map_plan(article: dict[str, Any]) -> bool:
    return bool(
        article.get("has_map_plan")
        or article.get("map_plan_pages")
        or ((article.get("detected_features") or {}).get("map_plan") or {}).get("present")
    )


def cave_token_pattern(token: str) -> str:
    if token.startswith("jaskyn"):
        return r"jaskyn(?:a|e|i|u|ou|am|ami|ach|iach)?"
    if token == "medvedia":
        return r"medved(?:ia|ej|iu|ou|ie|ich|im|i)?"
    if token == "medvedie":
        return r"medved(?:ie|ich|im|i|ia|ej|iu|ou)?"
    if token.isdigit():
        return re.escape(token)
    if len(token) <= 3:
        return re.escape(token)
    if len(token) <= 5:
        return f"{re.escape(token)}[a-z0-9]*"
    return f"{re.escape(token[:-1])}[a-z0-9]*"


def cave_phrase_pattern(cave_name: str) -> re.Pattern[str] | None:
    tokens = normalize_text(cave_name).split()
    if not tokens:
        return None
    parts = [cave_token_pattern(token) for token in tokens]
    return re.compile(rf"\b{' '.join(parts).replace(' ', r' +')}\b")


def article_text_for_cave_match(article: dict[str, Any]) -> str:
    values = [
        article.get("title") or "",
        article.get("abstract") or "",
    ]
    return normalize_text(" ".join(values))


def registered_match_prefix(token: str) -> str:
    return token[:5] if len(token) > 5 else token


def registered_name_prefixes(value: Any) -> list[str]:
    prefixes: list[str] = []
    for token in normalize_text(value).split():
        if len(token) < 3 or token in REGISTERED_MATCH_SKIP_TOKENS or token in CAVE_GENERIC_WORDS:
            continue
        prefix = registered_match_prefix(token)
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes


def article_registered_match_prefixes(article_text: str) -> list[str]:
    prefixes: list[str] = []
    for token in article_text.split():
        if len(token) < 3:
            continue
        prefix = registered_match_prefix(token)
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes


def cave_tokens_regex(tokens: list[str]) -> str:
    return r" +".join(cave_token_pattern(token) for token in tokens)


def registered_name_patterns(value: Any) -> list[re.Pattern[str]]:
    normalized = normalize_text(value)
    tokens = normalized.split()
    if not tokens or not any(token in CAVE_HEADWORD_KEYS for token in tokens):
        return []
    patterns: list[re.Pattern[str]] = []
    full_pattern = cave_phrase_pattern(value)
    if full_pattern:
        patterns.append(full_pattern)
    if len(tokens) > 1 and tokens[0] in CAVE_HEADWORD_KEYS:
        suffix_tokens = tokens[1:]
        if registered_name_prefixes(" ".join(suffix_tokens)):
            patterns.append(re.compile(rf"\b{cave_tokens_regex(suffix_tokens)} +cave\b"))
    if len(tokens) > 1 and tokens[-1] in CAVE_HEADWORD_KEYS:
        prefix_tokens = tokens[:-1]
        if registered_name_prefixes(" ".join(prefix_tokens)):
            patterns.append(re.compile(rf"\bcave +{cave_tokens_regex(prefix_tokens)}\b"))
    return patterns


def build_smopaj_text_matchers(
    data: dict[str, Any] | None,
    smopaj_lookup: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    entries = data.get("entries", []) if isinstance(data, dict) else []
    matchers_by_prefix: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    if not isinstance(entries, list):
        return matchers_by_prefix

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        official_name = str(entry.get("official_name") or "").strip()
        names = unique_strings([official_name, *list(entry.get("names") or []), *list(entry.get("aliases") or [])])
        for name in names:
            if not is_probable_cave_name(name):
                continue
            smopaj_entry = resolve_smopaj_entry(name, smopaj_lookup)
            if not smopaj_entry:
                continue
            canonical_name = str(smopaj_entry.get("official_name") or name).strip() or name
            patterns = registered_name_patterns(name)
            prefixes = registered_name_prefixes(name)
            if not patterns or not prefixes:
                continue
            matcher_key = (canonical_name, name)
            if matcher_key in seen:
                continue
            seen.add(matcher_key)
            matcher = {
                "name": canonical_name,
                "source_name": name,
                "patterns": patterns,
            }
            for prefix in prefixes:
                matchers_by_prefix[prefix].append(matcher)
    return matchers_by_prefix


def infer_registered_caves_from_article(
    article: dict[str, Any],
    matchers_by_prefix: dict[str, list[dict[str, Any]]],
) -> list[str]:
    if not matchers_by_prefix:
        return []
    text = article_text_for_cave_match(article)
    if not text:
        return []
    candidates: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for prefix in article_registered_match_prefixes(text):
        for matcher in matchers_by_prefix.get(prefix, []):
            key = (str(matcher.get("name") or ""), str(matcher.get("source_name") or ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append(matcher)

    matched: list[str] = []
    for matcher in candidates:
        patterns = matcher.get("patterns") or []
        if any(pattern.search(text) for pattern in patterns):
            matched.append(str(matcher.get("name") or ""))
    return unique_strings(matched)


def article_mentions_cave(article: dict[str, Any], cave_name: str) -> bool:
    if article.get("caves_verified"):
        return True
    pattern = cave_phrase_pattern(cave_name)
    if pattern is None:
        return False
    return bool(pattern.search(article_text_for_cave_match(article)))


def article_summary(article: dict[str, Any], cave_area: str = "") -> dict[str, Any]:
    summary = {
        "id": int(article["id"]),
        "title": article.get("title") or "",
        "year": article.get("year"),
        "volume": str(article.get("volume") or ""),
        "issue": str(article.get("issue") or ""),
        "pages": str(article.get("pages") or ""),
        "journal_id": str(article.get("journal_id") or DEFAULT_JOURNAL_ID),
        "journal_title": str(article.get("journal_title") or DEFAULT_JOURNAL_TITLE),
        "journal_short_title": str(article.get("journal_short_title") or DEFAULT_JOURNAL_SHORT_TITLE),
        "authors": unique_strings(article.get("authors") or []),
        "abstract": article.get("abstract") or "",
        "has_map_plan": has_map_plan(article),
        "map_plan_pages": article.get("map_plan_pages") or [],
        "pdf_url": article.get("pdf_url") or "",
        "pdf_link": pdf_link(article),
        "detail_url": f"/clanky/{article['id']}/",
    }
    if cave_area:
        summary["cave_area"] = cave_area
    return summary


def duplicate_article_key(article: dict[str, Any]) -> tuple[Any, ...]:
    return (
        article.get("journal_id") or DEFAULT_JOURNAL_ID,
        int(article.get("year") or 0),
        normalize_text(article.get("title") or ""),
        tuple(normalize_text(author) for author in article.get("authors", [])),
        normalize_text(article.get("pages") or ""),
    )


def duplicate_article_score(article: dict[str, Any]) -> tuple[int, int, int, int]:
    issue_key = normalize_text(article.get("issue") or "")
    has_clean_issue = int("chybne strankovanie" not in issue_key and "nove vydanie" not in issue_key)
    return (
        has_clean_issue,
        int(bool(article.get("pdf_link") or article.get("pdf_url"))),
        len(str(article.get("abstract") or "").strip()),
        int(article.get("id") or 0),
    )


def deduplicate_timeline_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for article in articles:
        key = duplicate_article_key(article)
        current = best_by_key.get(key)
        if current is None or duplicate_article_score(article) > duplicate_article_score(current):
            best_by_key[key] = article
    return list(best_by_key.values())


def build_cave_index(
    articles: list[dict[str, Any]],
    aliases: list[dict[str, Any]] | None = None,
    geomorphology: dict[str, Any] | None = None,
    smopaj_register: dict[str, Any] | None = None,
    smopaj_overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    alias_lookup = build_alias_lookup(aliases or [])
    area_region_lookup, cave_region_lookup = build_geomorphology_lookup(geomorphology or {})
    smopaj_lookup = build_smopaj_lookup(smopaj_register or {})
    smopaj_text_matchers = build_smopaj_text_matchers(smopaj_register or {}, smopaj_lookup)
    smopaj_override_lookup = build_smopaj_override_lookup(smopaj_overrides or {}, smopaj_register or {})
    smopaj_article_override_lookup = build_smopaj_article_override_lookup(smopaj_overrides or {}, smopaj_register or {})
    candidate_rows: list[dict[str, Any]] = []

    for article in articles:
        article_id = int(article.get("id") or 0)
        for cave_name in article_cave_candidates(article, smopaj_text_matchers):
            normalized_name = normalize_cave_candidate_name(cave_name, article)
            canonical_name = canonical_cave_name(normalized_name, alias_lookup)
            candidate_area = infer_cave_area(article, canonical_name)
            smopaj_article_override = resolve_smopaj_article_override(
                article_id,
                [canonical_name, normalized_name, cave_name],
                smopaj_article_override_lookup,
            )
            if smopaj_article_override and smopaj_article_override.get("cave_area"):
                candidate_area = str(smopaj_article_override.get("cave_area") or "").strip()
            smopaj_override = smopaj_article_override or resolve_smopaj_override(
                [canonical_name, normalized_name, cave_name],
                smopaj_override_lookup,
                candidate_area,
            )
            smopaj_entry = smopaj_override["entry"] if smopaj_override else resolve_smopaj_entry(canonical_name, smopaj_lookup)
            if smopaj_entry and not (smopaj_override and smopaj_override.get("preserve_name")):
                canonical_name = str(smopaj_entry.get("official_name") or canonical_name).strip() or canonical_name
            if smopaj_article_override and not smopaj_article_override.get("cave_area"):
                candidate_area = area_label_from_smopaj_entry(smopaj_entry)
            if not any(
                article_mentions_cave(article, name)
                for name in unique_strings([cave_name, normalized_name, canonical_name])
            ):
                continue
            candidate_rows.append(
                {
                    "article": article,
                    "source_name": cave_name,
                    "normalized_name": normalized_name,
                    "canonical_name": canonical_name,
                    "smopaj_entry": smopaj_entry,
                    "smopaj_override": smopaj_override,
                    "area": candidate_area,
                }
            )

    areas_by_name: defaultdict[str, set[str]] = defaultdict(set)
    smopaj_numbers_by_name: defaultdict[str, set[str]] = defaultdict(set)
    for row in candidate_rows:
        if row["area"]:
            areas_by_name[slugify(row["canonical_name"])].add(row["area"])
        if row["smopaj_entry"]:
            cave_number = str(row["smopaj_entry"].get("cave_number") or "").strip()
            if cave_number:
                smopaj_numbers_by_name[slugify(row["canonical_name"])].add(cave_number)

    area_split_names = {
        name_key
        for name_key, areas in areas_by_name.items()
        if should_keep_cave_area(name_key) and (len(areas) > 1 or name_key in AREA_SPLIT_CAVE_NAMES)
    }
    smopaj_split_names = {
        name_key
        for name_key, cave_numbers in smopaj_numbers_by_name.items()
        if len(cave_numbers) > 1
    }

    grouped: dict[str, dict[str, Any]] = {}
    slug_counts: defaultdict[str, int] = defaultdict(int)
    for row in candidate_rows:
        canonical_name = row["canonical_name"]
        source_name = row["source_name"]
        normalized_name = row["normalized_name"]
        name_key = slugify(canonical_name)
        smopaj_entry = row.get("smopaj_entry")
        smopaj_number = str(smopaj_entry.get("cave_number") or "").strip() if smopaj_entry else ""
        use_smopaj_key = bool(smopaj_number) and name_key in smopaj_split_names
        area = row["area"] if should_keep_cave_area(name_key) or use_smopaj_key else ""
        if use_smopaj_key and not area:
            area = area_label_from_smopaj_entry(smopaj_entry)
        use_area_key = bool(area) and name_key in area_split_names
        if use_smopaj_key:
            key = f"{name_key}--smopaj-{smopaj_number}"
            area_slug = slugify(area) if area else smopaj_number.replace(".", "-")
            slug_base = f"{name_key}-{area_slug}"
        elif use_area_key:
            key = f"{name_key}--{slugify(area)}"
            slug_base = f"{name_key}-{slugify(area)}"
        else:
            key = name_key
            slug_base = name_key
        if key not in grouped:
            slug_counts[slug_base] += 1
            slug = slug_base if slug_counts[slug_base] == 1 else f"{slug_base}-{slug_counts[slug_base]}"
            grouped[key] = {
                "name": canonical_name,
                "slug": slug,
                "aliases": set(),
                "articles": [],
                "area_counts": defaultdict(int),
                "smopaj_matches": [],
            }
        if row["smopaj_entry"]:
            grouped[key]["smopaj_matches"].append(
                {
                    "entry": row["smopaj_entry"],
                    "override": row.get("smopaj_override"),
                }
            )
        if area:
            grouped[key]["area_counts"][area] += 1
        if normalize_text(source_name) != normalize_text(canonical_name) and not is_contextual_cave_candidate(source_name):
            grouped[key]["aliases"].add(source_name)
        if normalize_text(normalized_name) != normalize_text(canonical_name) and not is_contextual_cave_candidate(normalized_name):
            grouped[key]["aliases"].add(normalized_name)
        grouped[key]["articles"].append(article_summary(row["article"], area))

    caves: list[dict[str, Any]] = []
    for cave in grouped.values():
        article_rows = sorted(
            deduplicate_timeline_articles(cave["articles"]),
            key=lambda item: (int(item.get("year") or 0), int(item.get("id") or 0)),
        )
        years = [int(item["year"]) for item in article_rows if item.get("year")]
        authors = {
            author
            for item in article_rows
            for author in item.get("authors", [])
            if author not in {"Anonymus", "Redakcia"}
        }
        area_counts = cave.get("area_counts") or {}
        cave_area = ""
        if area_counts:
            cave_area = sorted(area_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        cave_item = {
            "name": cave["name"],
            "slug": cave["slug"],
            "area": cave_area,
            "aliases": unique_strings(sorted(cave["aliases"])),
            "article_count": len(article_rows),
            "map_plan_count": sum(1 for item in article_rows if item.get("has_map_plan")),
            "first_year": min(years) if years else None,
            "last_year": max(years) if years else None,
            "authors_count": len(authors),
            "articles": article_rows,
        }
        smopaj_match = unique_smopaj_match(list(cave.get("smopaj_matches") or []))
        smopaj_entry = smopaj_match.get("entry") if smopaj_match else None
        if smopaj_entry:
            cave_item["smopaj_cave_number"] = str(smopaj_entry.get("cave_number") or "").strip()
            if smopaj_entry.get("registry_number"):
                cave_item["smopaj_registry_number"] = str(smopaj_entry.get("registry_number") or "").strip()
            official_name = str(smopaj_entry.get("official_name") or "").strip()
            if official_name and normalize_text(official_name) != normalize_text(cave_item["name"]):
                cave_item["smopaj_official_name"] = official_name
            smopaj_override = smopaj_match.get("override") if smopaj_match else None
            if smopaj_override:
                cave_item["smopaj_match_source"] = str(smopaj_override.get("match_source") or "curated-override")
                if smopaj_override.get("confidence"):
                    cave_item["smopaj_match_confidence"] = str(smopaj_override.get("confidence") or "").strip()
                if smopaj_override.get("note"):
                    cave_item["smopaj_match_note"] = str(smopaj_override.get("note") or "").strip()
        region = resolve_geomorphology(cave["name"], cave_area, area_region_lookup, cave_region_lookup)
        if not region and smopaj_entry:
            region = region_from_smopaj_entry(smopaj_entry)
        if region:
            cave_item["region"] = region
        caves.append(cave_item)

    return sorted(
        caves,
        key=lambda item: (-int(item["article_count"]), str(item["name"]).casefold()),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES_PATH)
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIASES_PATH)
    parser.add_argument("--geomorphology", type=Path, default=DEFAULT_GEOMORPHOLOGY_PATH)
    parser.add_argument("--smopaj-register", type=Path, default=DEFAULT_SMOPAJ_REGISTER_PATH)
    parser.add_argument("--smopaj-overrides", type=Path, default=DEFAULT_SMOPAJ_OVERRIDES_PATH)
    parser.add_argument("--smopaj-ai-matches", type=Path, default=DEFAULT_SMOPAJ_AI_MATCHES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    articles = json.loads(args.articles.read_text(encoding="utf-8"))
    aliases = load_cave_aliases(args.aliases)
    geomorphology = load_geomorphology(args.geomorphology)
    smopaj_register = load_smopaj_cave_register(args.smopaj_register)
    smopaj_overrides = load_smopaj_cave_match_overrides(args.smopaj_overrides)
    smopaj_ai_matches = load_smopaj_cave_match_overrides(args.smopaj_ai_matches)
    smopaj_matches = merge_smopaj_match_sources(smopaj_overrides, smopaj_ai_matches)
    caves = build_cave_index(articles, aliases, geomorphology, smopaj_register, smopaj_matches)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(caves, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "caves": len(caves),
                "alias_groups": len(aliases),
                "geomorphology_regions": sum(1 for cave in caves if cave.get("region")),
                "smopaj_matches": sum(1 for cave in caves if cave.get("smopaj_cave_number")),
                "smopaj_curated_matches": sum(1 for cave in caves if cave.get("smopaj_match_source") == "curated-override"),
                "smopaj_ai_matches": sum(1 for cave in caves if cave.get("smopaj_match_source") == "ai-generated-override"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
