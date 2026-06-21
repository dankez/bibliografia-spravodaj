#!/usr/bin/env python3
"""Detect article-level research features from local Spravodaj SSS data.

The script deliberately uses local metadata and already extracted full text
first. Optional visual/Ollama classification is only a second-pass helper for
uncertain PDF pages.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
ARTICLES_PATH = BASE_DIR / "data" / "articles_with_urls.json"
WEB_ARTICLES_PATH = BASE_DIR / "web" / "src" / "data" / "articles.json"
FULLTEXT_PATH = BASE_DIR / "data" / "article_fulltext.jsonl"
OUTPUT_PATH = BASE_DIR / "data" / "article_feature_detection.jsonl"
CANDIDATES_PATH = BASE_DIR / "data" / "map_plan_candidates.jsonl"
SUMMARY_PATH = BASE_DIR / "data" / "article_feature_detection_summary.json"
RENDER_DIR = BASE_DIR / "data" / "map_plan_pages"


FEATURE_THRESHOLDS = {
    "map_plan": 0.85,
    "photo": 0.55,
    "table": 0.55,
    "bibliography": 0.55,
    "measurement_data": 0.50,
    "coordinates": 0.50,
    "cross_section": 0.55,
}
MAP_PLAN_CANDIDATE_THRESHOLD = 0.38

FEATURE_TAGS = {
    "map_plan": "mapa/plán",
    "photo": "obrazová dokumentácia",
    "table": "tabuľky",
    "bibliography": "literatúra",
    "measurement_data": "meračské údaje",
    "coordinates": "súradnice",
    "cross_section": "rez/profil",
}

SCALE_RE = re.compile(r"(?:(?:mierka|m)\s*[:.]?\s*)?1\s*[:/]\s*\d{2,5}\b")
NEGATIVE_PLAN_RE = re.compile(
    r"\bplan\s+(?:prace|cinnosti|akcii|akcie|zasadnutia|vystavby|rozvoja|podujati|vyletu)\b"
)
COORDINATE_RE = re.compile(
    r"(?:\b(?:gps|wgs|jtsk|s-jtsk|suradnic)\b|"
    r"\b[xy]\s*[:=]\s*-?\d{5,7}(?:[,.]\d+)?|"
    r"\b\d{1,2}\s*[°º]\s*\d{1,2}\s*['’´]\s*\d{1,2}(?:[,.]\d+)?|"
    r"\b[NS]\s*\d{1,2}(?:[,.]\d+)?\s+[EW]\s*\d{1,3}(?:[,.]\d+)?)"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = fold_text(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def fold_text(value: str) -> str:
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", str(value))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    return re.sub(r"\s+", " ", text).strip()


def empty_feature(score: float = 0.0) -> dict[str, Any]:
    return {
        "present": False,
        "score": score,
        "confidence": "none",
        "pages": [],
        "evidence": [],
        "methods": [],
    }


def empty_features() -> dict[str, dict[str, Any]]:
    return {feature: empty_feature() for feature in FEATURE_THRESHOLDS}


def add_signal(
    features: dict[str, dict[str, Any]],
    feature: str,
    score: float,
    evidence: str,
    method: str,
    page: int | None = None,
) -> None:
    item = features[feature]
    item["score"] = max(float(item.get("score") or 0.0), min(1.0, score))
    if evidence and evidence not in item["evidence"]:
        item["evidence"].append(evidence)
    if method and method not in item["methods"]:
        item["methods"].append(method)
    if page is not None and page not in item["pages"]:
        item["pages"].append(page)


def score_metadata(article: dict[str, Any]) -> dict[str, dict[str, Any]]:
    features = empty_features()
    extras = " ".join(str(item) for item in as_list(article.get("extras")))
    title = str(article.get("title") or "")
    abstract = str(article.get("abstract") or "")
    folded_extras = fold_text(extras)
    folded_title = fold_text(title)
    folded_metadata = fold_text(" ".join([extras, title, abstract]))

    if re.search(r"\b\d*\s*pl\.\s*j\.", folded_extras):
        add_signal(features, "map_plan", 0.98, "metadata: pl. j.", "metadata")
    if re.search(r"\b\d*\s*(?:mapa|mapy|mapiek)\b|\b\d*\s*pl[aá]n(?:ov|y)?\b|\bpodorys\b", folded_extras):
        add_signal(features, "map_plan", 0.92, "metadata: mapa/plán v prílohách", "metadata")
    if re.search(r"\bmapa\b|\bmapy\b|\bplan\s+jaskyn|\bplan\s+priepast|\bpodorys\b", folded_metadata):
        if not NEGATIVE_PLAN_RE.search(folded_title):
            add_signal(features, "map_plan", 0.52, "metadata: mapa/plán v texte názvu/anotácie", "metadata")
    if re.search(r"\bprofil\b|\brez\b", folded_metadata):
        add_signal(features, "cross_section", 0.60, "metadata: rez/profil", "metadata")
        if re.search(r"\bmierka\b|\bplan\b|\bpodorys\b|\bmapa\b", folded_metadata):
            add_signal(features, "map_plan", 0.50, "metadata: rez/profil s mapovým kontextom", "metadata")

    if re.search(r"\b\d*\s*obr\.|\bfoto|\bfotograf|\bsnimk|\bobraz", folded_extras):
        add_signal(features, "photo", 0.85, "metadata: obr./foto", "metadata")
    if re.search(r"\btab\.|\btabulka|\btabulky", folded_extras):
        add_signal(features, "table", 0.82, "metadata: tab.", "metadata")
    if re.search(r"\blit\.|\bliteratura|\bbibliograf", folded_extras):
        add_signal(features, "bibliography", 0.80, "metadata: lit.", "metadata")

    return features


def score_text_page(text: str, page: int | None = None) -> dict[str, dict[str, Any]]:
    features = empty_features()
    folded = fold_text(text)
    if not folded:
        return features

    has_scale = bool(SCALE_RE.search(folded))
    has_plan_word = bool(
        re.search(
            r"\b(?:mapa|mapy|mapovy|plan|podorys|nacrt|situacia|topografia|topograficky)\b",
            folded,
        )
    )
    has_specific_plan = bool(
        re.search(
            r"\b(?:plan|podorys|mapa)\s+(?:jaskyn|priepast|chodieb|systemu|lokality)|"
            r"\bjaskynny\s+plan|\bmapovy\s+nacrt",
            folded,
        )
    )
    has_survey = bool(
        re.search(
            r"\b(?:meral|merali|zameral|zamerali|zameranie|mapoval|mapovali|"
            r"kreslil|kreslili|kresba|zostavil|digitalizoval)\b",
            folded,
        )
    )
    has_geometry = bool(
        re.search(
            r"\b(?:polygon|polygonovy|polygonom|meracsky\s+bod|azimut|"
            r"stanovisko|traverz|legenda)\b",
            folded,
        )
    )
    has_dimensions = bool(
        re.search(
            r"\b(?:dlzka|hlbka|prevysenie|nadmorska\s+vyska|rozmery|denivelacia)\b",
            folded,
        )
    )
    has_cross_section = bool(re.search(r"\b(?:rez|profil|priecny\s+rez|pozdlzny\s+rez)\b", folded))
    has_cave_context = bool(re.search(r"\b(?:jaskyn|priepast|chodba|sifon|komin|dolina|kras)\b", folded))
    has_map_drawing_word = bool(re.search(r"\b(?:mapa|mapy|mapovy|podorys|nacrt|situacia|topografia)\b", folded))
    negative_plan = bool(NEGATIVE_PLAN_RE.search(folded))

    map_score = 0.0
    if has_specific_plan:
        map_score += 0.55
        add_signal(features, "map_plan", map_score, "text: plán/pôdorys jaskyne", "text", page)
    if has_scale:
        map_score += 0.42
        add_signal(features, "map_plan", map_score, "text: mierka 1:n", "text", page)
    if has_plan_word and not negative_plan and not has_specific_plan:
        map_score += 0.26
        add_signal(features, "map_plan", map_score, "text: mapa/plán/pôdorys", "text", page)
    if has_survey:
        map_score += 0.18
        add_signal(features, "map_plan", map_score, "text: merali/kreslili/zamerali", "text", page)
    if has_geometry:
        map_score += 0.18
        add_signal(features, "map_plan", map_score, "text: legenda/polygón/meračské body", "text", page)
    if has_dimensions and (has_plan_word or has_scale or has_geometry or has_survey):
        map_score += 0.10
        add_signal(features, "map_plan", map_score, "text: dĺžka/hĺbka/prevýšenie", "text", page)
    if has_cross_section and (has_cave_context or has_scale):
        add_signal(features, "cross_section", 0.68, "text: rez/profil", "text", page)
        map_score += 0.18
        add_signal(features, "map_plan", map_score, "text: rez/profil", "text", page)
    if negative_plan and not (has_scale or has_specific_plan or has_geometry or has_survey):
        features["map_plan"]["score"] = min(float(features["map_plan"]["score"]), 0.25)
        features["map_plan"]["evidence"].append("guard: plán činnosti/práce")
    strong_map_context = has_scale and (
        has_specific_plan or has_geometry or has_survey or has_cross_section or has_map_drawing_word
    )
    survey_map_context = has_specific_plan and (has_survey or has_geometry or has_cross_section)
    if not strong_map_context and not survey_map_context:
        features["map_plan"]["score"] = min(float(features["map_plan"]["score"]), 0.62)
        if features["map_plan"]["score"] > 0:
            features["map_plan"]["evidence"].append("guard: chýba mierka alebo meračský kontext")
    elif has_scale and has_map_drawing_word and not (has_specific_plan or has_survey or has_geometry or has_cross_section):
        features["map_plan"]["score"] = min(float(features["map_plan"]["score"]), 0.68)
        features["map_plan"]["evidence"].append("guard: iba mierka + všeobecná mapa/plán")

    if re.search(r"\b(?:obr\.|obrazok|obrazky|foto|fotograf|snimka|snimky)\b", folded):
        add_signal(features, "photo", 0.66, "text: obr./foto/snímka", "text", page)
    if re.search(r"\b(?:tab\.|tabulka|tabulky|tabulkou)\b", folded):
        add_signal(features, "table", 0.70, "text: tabuľka", "text", page)
    if looks_like_table_text(text):
        add_signal(features, "table", 0.62, "text: tabuľkové riadky", "text", page)
    if re.search(r"\b(?:lit\.|literatura|pouzita\s+literatura|zoznam\s+literatury|bibliografia)\b", folded):
        add_signal(features, "bibliography", 0.72, "text: literatúra", "text", page)
    if has_dimensions:
        add_signal(features, "measurement_data", 0.58, "text: rozmery jaskyne", "text", page)
    if re.search(r"\b(?:m\s*n\.\s*m\.|m\.n\.m\.|nadmorska\s+vyska|azimut|sklon)\b", folded):
        add_signal(features, "measurement_data", 0.62, "text: výškové/meračské údaje", "text", page)
    if COORDINATE_RE.search(folded):
        add_signal(features, "coordinates", 0.72, "text: súradnice", "text", page)
        add_signal(features, "measurement_data", 0.62, "text: súradnice", "text", page)

    return features


def looks_like_table_text(text: str) -> bool:
    rows = 0
    for line in text.splitlines():
        cells = [cell for cell in re.split(r"\s{2,}|\t+", line.strip()) if cell]
        numeric_cells = sum(1 for cell in cells if re.search(r"\d", cell))
        if len(cells) >= 3 and numeric_cells >= 2:
            rows += 1
        if rows >= 3:
            return True
    return False


def merge_features(target: dict[str, dict[str, Any]], source: dict[str, dict[str, Any]]) -> None:
    for feature, payload in source.items():
        item = target[feature]
        item["score"] = max(float(item.get("score") or 0.0), float(payload.get("score") or 0.0))
        source_pages = as_list(payload.get("pages"))
        if feature == "map_plan" and float(payload.get("score") or 0.0) < FEATURE_THRESHOLDS["map_plan"]:
            source_pages = []
        item["pages"] = sorted(set(as_list(item.get("pages")) + source_pages))
        item["evidence"] = unique(as_list(item.get("evidence")) + as_list(payload.get("evidence")))[:18]
        item["methods"] = unique(as_list(item.get("methods")) + as_list(payload.get("methods")))


def split_fulltext_pages(record: dict[str, Any]) -> list[tuple[int | None, str]]:
    text = record.get("text") or ""
    if not text:
        return []
    start = record.get("pdf_page_start")
    try:
        physical_start = int(start) if start else None
    except (TypeError, ValueError):
        physical_start = None
    pages = text.split("\f")
    result: list[tuple[int | None, str]] = []
    for index, page_text in enumerate(pages):
        physical_page = physical_start + index if physical_start is not None else None
        if page_text.strip():
            result.append((physical_page, page_text))
    return result


def finalize_features(features: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    for feature, payload in features.items():
        score = round(min(1.0, max(0.0, float(payload.get("score") or 0.0))), 3)
        threshold = FEATURE_THRESHOLDS[feature]
        payload["score"] = score
        payload["present"] = score >= threshold
        if score >= 0.85:
            payload["confidence"] = "high"
        elif score >= threshold:
            payload["confidence"] = "medium"
        elif feature == "map_plan" and score >= MAP_PLAN_CANDIDATE_THRESHOLD:
            payload["confidence"] = "candidate"
        elif score > 0:
            payload["confidence"] = "low"
        else:
            payload["confidence"] = "none"
        payload["pages"] = sorted(int(page) for page in payload.get("pages") or [] if page is not None)
        payload["evidence"] = unique(payload.get("evidence") or [])[:18]
        payload["methods"] = unique(payload.get("methods") or [])
    return features


def detect_article(article: dict[str, Any], fulltext_record: dict[str, Any] | None) -> dict[str, Any]:
    features = score_metadata(article)
    if fulltext_record:
        for page, page_text in split_fulltext_pages(fulltext_record):
            merge_features(features, finalize_features(score_text_page(page_text, page)))
    features = finalize_features(features)
    map_feature = features["map_plan"]
    return {
        "id": article.get("id"),
        "title": article.get("title", ""),
        "year": article.get("year"),
        "issue": article.get("issue", ""),
        "pages": article.get("pages", ""),
        "pdf_url": article.get("pdf_url", ""),
        "pdf_cache": fulltext_record.get("pdf_cache") if fulltext_record else "",
        "has_map_plan": bool(map_feature["present"]),
        "map_plan_score": map_feature["score"],
        "map_plan_pages": map_feature["pages"],
        "features": features,
    }


def pdf_cache_path(record: dict[str, Any]) -> Path | None:
    pdf_cache = record.get("pdf_cache")
    if not pdf_cache:
        return None
    path = Path(str(pdf_cache))
    if not path.is_absolute():
        path = BASE_DIR / path
    return path if path.exists() else None


def render_pdf_page(pdf_path: Path, page: int, render_dir: Path, dpi: int = 110) -> Path | None:
    if not shutil.which("pdftoppm"):
        return None
    render_dir.mkdir(parents=True, exist_ok=True)
    prefix = render_dir / f"{pdf_path.stem}_p{page}"
    output = prefix.with_suffix(".png")
    if output.exists() and output.stat().st_size > 0:
        return output
    cmd = [
        "pdftoppm",
        "-f",
        str(page),
        "-l",
        str(page),
        "-singlefile",
        "-png",
        "-r",
        str(dpi),
        str(pdf_path),
        str(prefix),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output.exists():
        return None
    return output


def visual_page_score(image_path: Path) -> tuple[float, list[str]]:
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        return 0.0, ["visual: PIL/numpy unavailable"]

    image = Image.open(image_path).convert("L")
    image.thumbnail((1200, 1200))
    arr = np.asarray(image, dtype=np.int16)
    if arr.size == 0:
        return 0.0, ["visual: empty image"]

    white_ratio = float((arr > 238).mean())
    dark_ratio = float((arr < 90).mean())
    horizontal_edges = np.abs(np.diff(arr, axis=1)) > 35
    vertical_edges = np.abs(np.diff(arr, axis=0)) > 35
    edge_ratio = float((horizontal_edges.mean() + vertical_edges.mean()) / 2)

    score = 0.0
    if white_ratio >= 0.70:
        score += 0.22
    if 0.008 <= dark_ratio <= 0.22:
        score += 0.18
    if edge_ratio >= 0.035:
        score += 0.30
    if edge_ratio >= 0.060:
        score += 0.12
    if white_ratio >= 0.78 and edge_ratio >= 0.035:
        score += 0.12
    if dark_ratio > 0.35 or white_ratio < 0.45:
        score = min(score, 0.28)

    evidence = [
        f"visual:white={white_ratio:.2f}",
        f"visual:dark={dark_ratio:.2f}",
        f"visual:edges={edge_ratio:.3f}",
    ]
    return min(1.0, score), evidence


def apply_visual_pass(
    result: dict[str, Any],
    fulltext_record: dict[str, Any],
    render_dir: Path,
    mode: str,
) -> None:
    feature = result["features"]["map_plan"]
    score = float(feature["score"])
    if mode == "candidates" and not (MAP_PLAN_CANDIDATE_THRESHOLD <= score < FEATURE_THRESHOLDS["map_plan"]):
        return
    pages = feature.get("pages") or []
    if not pages:
        start = fulltext_record.get("pdf_page_start")
        end = fulltext_record.get("pdf_page_end") or start
        try:
            pages = list(range(int(start), int(end) + 1))[:3] if start else []
        except (TypeError, ValueError):
            pages = []
    pdf_path = pdf_cache_path(fulltext_record)
    if not pdf_path:
        return
    for page in pages:
        image_path = render_pdf_page(pdf_path, int(page), render_dir)
        if not image_path:
            continue
        visual_score, evidence = visual_page_score(image_path)
        if visual_score >= 0.58:
            add_signal(result["features"], "map_plan", max(score, visual_score), "visual: technický výkres", "visual", int(page))
        elif visual_score > 0:
            add_signal(result["features"], "map_plan", max(score, min(0.55, visual_score)), evidence[0], "visual", int(page))
        for item in evidence:
            if item not in feature["evidence"]:
                feature["evidence"].append(item)
    result["features"] = finalize_features(result["features"])
    feature = result["features"]["map_plan"]
    result["has_map_plan"] = bool(feature["present"])
    result["map_plan_score"] = feature["score"]
    result["map_plan_pages"] = feature["pages"]


def classify_image_with_ollama(image_path: Path, model: str, timeout: int = 120) -> dict[str, Any] | None:
    prompt = (
        "Classify this rendered page from a caving journal. "
        "Return only JSON with keys map_plan boolean, confidence one of low/medium/high, "
        "and reasons array. True means the page contains a cave map, cave plan, survey drawing, "
        "technical line plan, cross-section, profile, legend, or scale drawing. "
        "False means ordinary text, photo, cover, table, or administrative plan-of-work text."
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(image_path.read_bytes()).decode("ascii")],
            }
        ],
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}
    content = ((body.get("message") or {}).get("content") or body.get("response") or "").strip()
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {"raw": content}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"raw": content}


def apply_ollama_pass(
    result: dict[str, Any],
    fulltext_record: dict[str, Any],
    render_dir: Path,
    model: str,
    max_pages: int,
) -> int:
    if max_pages <= 0:
        return 0
    feature = result["features"]["map_plan"]
    score = float(feature["score"])
    if not (MAP_PLAN_CANDIDATE_THRESHOLD <= score < FEATURE_THRESHOLDS["map_plan"]):
        return 0
    pages = feature.get("pages") or []
    if not pages:
        start = fulltext_record.get("pdf_page_start")
        try:
            pages = [int(start)] if start else []
        except (TypeError, ValueError):
            pages = []
    pdf_path = pdf_cache_path(fulltext_record)
    if not pdf_path:
        return 0
    calls = 0
    for page in pages[:max_pages]:
        image_path = render_pdf_page(pdf_path, int(page), render_dir, dpi=130)
        if not image_path:
            continue
        response = classify_image_with_ollama(image_path, model)
        calls += 1
        if not response or response.get("error"):
            add_signal(result["features"], "map_plan", score, "ollama: unavailable", "ollama", int(page))
            continue
        is_map = bool(response.get("map_plan"))
        confidence = str(response.get("confidence") or "low").casefold()
        reasons = "; ".join(str(item) for item in as_list(response.get("reasons"))[:3])
        if is_map:
            ollama_score = 0.88 if confidence == "high" else 0.76
            add_signal(result["features"], "map_plan", ollama_score, f"ollama:{model}: {reasons}", "ollama", int(page))
        elif score < FEATURE_THRESHOLDS["map_plan"]:
            result["features"]["map_plan"]["score"] = min(score, 0.34)
            add_signal(result["features"], "map_plan", 0.34, f"ollama:{model}: not map/plan", "ollama", int(page))
    result["features"] = finalize_features(result["features"])
    feature = result["features"]["map_plan"]
    result["has_map_plan"] = bool(feature["present"])
    result["map_plan_score"] = feature["score"]
    result["map_plan_pages"] = feature["pages"]
    return calls


def load_fulltext(path: Path) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for record in iter_jsonl(path) or []:
        article_id = record.get("id")
        if isinstance(article_id, int):
            records[article_id] = record
    return records


def candidate_records(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for result in results:
        score = float(result["features"]["map_plan"]["score"])
        if MAP_PLAN_CANDIDATE_THRESHOLD <= score < FEATURE_THRESHOLDS["map_plan"]:
            candidates.append(
                {
                    "id": result["id"],
                    "title": result["title"],
                    "year": result["year"],
                    "issue": result["issue"],
                    "pages": result["pages"],
                    "score": score,
                    "pdf_cache": result.get("pdf_cache"),
                    "map_plan_pages": result.get("map_plan_pages") or [],
                    "evidence": result["features"]["map_plan"]["evidence"],
                }
            )
    return candidates


def update_articles_with_results(articles: list[dict[str, Any]], results_by_id: dict[int, dict[str, Any]]) -> int:
    updated = 0
    now = utc_now()
    for article in articles:
        result = results_by_id.get(article.get("id"))
        if not result:
            continue
        detected = dict(article.get("detected_features") or {})
        for feature, payload in result["features"].items():
            detected[feature] = {
                "present": payload["present"],
                "score": payload["score"],
                "confidence": payload["confidence"],
                "pages": payload["pages"],
                "evidence": payload["evidence"],
                "methods": payload["methods"],
                "updated_at": now,
            }
        managed_tags = set(FEATURE_TAGS.values())
        tags = [tag for tag in unique(as_list(article.get("tags"))) if tag not in managed_tags]
        for feature, payload in result["features"].items():
            if payload["present"]:
                tags = unique(tags + [FEATURE_TAGS[feature]])
        article["tags"] = tags
        article["detected_features"] = detected
        article["has_map_plan"] = bool(result["features"]["map_plan"]["present"])
        article["map_plan_score"] = result["features"]["map_plan"]["score"]
        article["map_plan_pages"] = result["features"]["map_plan"]["pages"]
        updated += 1
    return updated


def summarize(results: list[dict[str, Any]], candidates: list[dict[str, Any]], ollama_calls: int) -> dict[str, Any]:
    feature_counts = {
        feature: sum(1 for result in results if result["features"][feature]["present"])
        for feature in FEATURE_THRESHOLDS
    }
    return {
        "generated_at": utc_now(),
        "articles": len(results),
        "feature_counts": feature_counts,
        "map_plan_candidates": len(candidates),
        "ollama_calls": ollama_calls,
        "thresholds": FEATURE_THRESHOLDS,
        "candidate_threshold": MAP_PLAN_CANDIDATE_THRESHOLD,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect maps/plans and other research features from local Spravodaj SSS metadata/full text."
    )
    parser.add_argument("--articles", default=str(ARTICLES_PATH), help="Input article JSON.")
    parser.add_argument("--fulltext", default=str(FULLTEXT_PATH), help="Input article fulltext JSONL.")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Feature detection JSONL output.")
    parser.add_argument("--candidates-output", default=str(CANDIDATES_PATH), help="Uncertain map/plan candidates JSONL.")
    parser.add_argument("--summary-output", default=str(SUMMARY_PATH), help="Summary JSON output.")
    parser.add_argument("--web-articles", default=str(WEB_ARTICLES_PATH), help="Frontend article JSON to sync.")
    parser.add_argument("--limit", type=int, help="Limit number of articles for a test run.")
    parser.add_argument("--write", action="store_true", help="Update article JSON files with detected features.")
    parser.add_argument("--no-sync-web", action="store_true", help="Do not update web/src/data/articles.json on --write.")
    parser.add_argument("--visual", action="store_true", help="Render candidate PDF pages and apply local image heuristics.")
    parser.add_argument(
        "--visual-mode",
        choices=["candidates", "all"],
        default="candidates",
        help="Which map/plan records get visual image heuristics.",
    )
    parser.add_argument("--render-dir", default=str(RENDER_DIR), help="Directory for rendered PDF page images.")
    parser.add_argument("--ollama-model", default="", help="Optional local Ollama vision model for uncertain pages.")
    parser.add_argument(
        "--max-ollama-pages",
        type=int,
        default=0,
        help="Maximum rendered pages per article to classify with Ollama. 0 disables Ollama calls.",
    )
    args = parser.parse_args()

    articles_path = Path(args.articles)
    fulltext_path = Path(args.fulltext)
    output_path = Path(args.output)
    candidates_path = Path(args.candidates_output)
    summary_path = Path(args.summary_output)
    render_dir = Path(args.render_dir)

    articles = read_json(articles_path)
    if args.limit:
        articles = articles[: args.limit]
    fulltext = load_fulltext(fulltext_path)

    results: list[dict[str, Any]] = []
    ollama_calls = 0
    for article in articles:
        record = fulltext.get(article.get("id"))
        result = detect_article(article, record)
        if record and args.visual:
            apply_visual_pass(result, record, render_dir, args.visual_mode)
        if record and args.ollama_model:
            ollama_calls += apply_ollama_pass(
                result,
                record,
                render_dir,
                args.ollama_model,
                args.max_ollama_pages,
            )
        results.append(result)

    candidates = candidate_records(results)
    write_jsonl(output_path, results)
    write_jsonl(candidates_path, candidates)
    summary = summarize(results, candidates, ollama_calls)
    write_json(summary_path, summary)

    updated = 0
    synced_web = 0
    if args.write:
        full_articles = read_json(articles_path)
        results_by_id = {int(result["id"]): result for result in results if isinstance(result.get("id"), int)}
        updated = update_articles_with_results(full_articles, results_by_id)
        write_json(articles_path, full_articles)
        if not args.no_sync_web:
            web_path = Path(args.web_articles)
            if web_path.exists():
                web_articles = read_json(web_path)
                synced_web = update_articles_with_results(web_articles, results_by_id)
                write_json(web_path, web_articles)

    print(
        "Done. "
        f"articles={len(results)}, map_plans={summary['feature_counts']['map_plan']}, "
        f"candidates={len(candidates)}, updated={updated}, synced_web={synced_web}, "
        f"ollama_calls={ollama_calls}, output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
