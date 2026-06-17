#!/usr/bin/env python3
"""Hybrid map/plan detector: local prefilter + optional MiniCPM confirmation.

The prefilter is deliberately cheap and local: page text from pdftotext plus
simple visual metrics from rendered page images. The vision model is called
only for candidate pages.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ai_detect_pdf_maps import (
    BASE_DIR,
    OUTPUT_DIR,
    classify_image,
    load_issue_articles,
    load_issue_fulltext,
    pdf_page_count,
    render_pdf_page,
    resolve_pdf_path,
    selected_pages,
    write_json,
    write_jsonl,
)


DEFAULT_MODEL = "minicpm-v4.6"
DEFAULT_OCR_LANGUAGES = "slk+ces"
MAP_OCR_RE = re.compile(
    r"\b(?:"
    r"mapa|mapka|mapoval\w*|mapovan\w*|"
    r"podorys|plan|profil|rez|prierez|nacrt|"
    r"zameral\w*|meral\w*|kreslil\w*|kresba|"
    r"mierka|meritko|legenda|polygon|polyg[oó]n|"
    r"dlzka|hlbka|prevysenie|azimut|"
    r"1\s*[:/]\s*\d{2,5}"
    r")\b"
)
PHOTO_OCR_RE = re.compile(r"\b(?:foto|fotografia|snimka|snímka|autor\s+foto|photo)\b")
ADMIN_PLAN_RE = re.compile(
    r"\bplan\s+(?:prace|cinnosti|akcii|akcie|zasadnutia|vystavby|rozvoja|podujati|vyletu)\b"
)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def fold_text(value: str) -> str:
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", str(value))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    return re.sub(r"\s+", " ", text).strip()


def resolve_ocr_languages(requested: str) -> str:
    if not shutil.which("tesseract"):
        return ""
    result = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    available = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("List of available")
    }
    selected = [
        language
        for language in re.split(r"[+, ]+", requested.strip())
        if language and language in available
    ]
    if not selected and "slk" in available:
        selected = ["slk"]
    return "+".join(dict.fromkeys(selected))


def pdftotext_page(pdf_path: Path, page: int) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc
    return records


def pdftotext_bbox_page(pdf_path: Path, page: int) -> dict[str, Any]:
    result = subprocess.run(
        ["pdftotext", "-bbox-layout", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"width": 0.0, "height": 0.0, "lines": []}

    try:
        root = ET.fromstring(result.stdout)
    except ET.ParseError:
        return {"width": 0.0, "height": 0.0, "lines": []}

    page_node = next((node for node in root.iter() if node.tag.endswith("page")), None)
    if page_node is None:
        return {"width": 0.0, "height": 0.0, "lines": []}

    def number(node: ET.Element, key: str) -> float:
        try:
            return float(node.attrib[key])
        except (KeyError, TypeError, ValueError):
            return 0.0

    lines: list[dict[str, Any]] = []
    for line in page_node.iter():
        if not line.tag.endswith("line"):
            continue
        words = []
        for word in line:
            if not word.tag.endswith("word"):
                continue
            text = word.text or ""
            if not text.strip():
                continue
            words.append(
                {
                    "text": text,
                    "xMin": number(word, "xMin"),
                    "yMin": number(word, "yMin"),
                    "xMax": number(word, "xMax"),
                    "yMax": number(word, "yMax"),
                }
            )
        if not words:
            continue
        lines.append(
            {
                "text": " ".join(item["text"] for item in words),
                "xMin": number(line, "xMin"),
                "yMin": number(line, "yMin"),
                "xMax": number(line, "xMax"),
                "yMax": number(line, "yMax"),
                "words": words,
            }
        )

    return {
        "width": number(page_node, "width"),
        "height": number(page_node, "height"),
        "lines": lines,
    }


def map_caption_candidates(pdf_path: Path, page: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    layout = pdftotext_bbox_page(pdf_path, page)
    candidates = []
    for line in layout["lines"]:
        text = line["text"]
        if not is_map_caption(text):
            continue
        start_index = map_keyword_index(line["words"])
        words = line["words"][start_index:] if start_index is not None else line["words"]
        if not words:
            continue
        candidates.append(
            {
                "text": " ".join(item["text"] for item in words),
                "line_text": text,
                "bbox": {
                    "xMin": min(item["xMin"] for item in words),
                    "yMin": min(item["yMin"] for item in words),
                    "xMax": max(item["xMax"] for item in words),
                    "yMax": max(item["yMax"] for item in words),
                },
            }
        )
    return layout, candidates


def map_keyword_index(words: list[dict[str, Any]]) -> int | None:
    for index, word in enumerate(words):
        token = fold_text(re.sub(r"^[^\wÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž]+|[^\w]+$", "", word["text"]))
        if token in {"mapa", "mapka", "podorys", "plan", "rez", "prierez", "nacrt", "profil"}:
            return index
    return None


def text_map_score(text: str) -> tuple[float, list[str]]:
    folded = fold_text(text)
    score = 0.0
    reasons: list[str] = []

    def add(weight: float, reason: str) -> None:
        nonlocal score
        score += weight
        reasons.append(reason)

    caption_lines = likely_caption_lines(text)
    map_caption_lines = [
        line for line in caption_lines
        if is_map_caption(line) and not is_photo_caption(line)
    ]
    photo_caption_lines = [line for line in caption_lines if is_photo_caption(line)]

    if map_caption_lines:
        add(4.0, "caption: mapový popis pod objektom")
    elif re.search(r"\bmap(?:a|ka)\b", folded):
        add(1.6, "text: mapa/mapka")
    if re.search(r"\bpodorys\b|\bplan\b|\brozvinuty rez\b|\bprierez\b|\bprofil\b|\brez na rovinu\b", folded):
        add(1.4, "text: pôdorys/plán/rez/profil")
    if re.search(r"\bmierka\b|\bmeritko\b|\b1\s*[:/]\s*\d{2,5}\b", folded):
        add(0.8, "text: mierka/scale")
    if re.search(r"\bzameral(?:i)?\b|\bkreslil(?:i)?\b|\bzamerane\b|\bdokumentovali\b", folded):
        add(0.7, "text: zameral/kreslil/dokumentovali")
    if re.search(r"\blegenda\b|\bpolyg[oó]n\b|\bmeracsk", folded):
        add(0.7, "text: legenda/meračský kontext")
    if re.search(r"\bdlzka\b|\bhlbka\b|\bprevysenie\b", folded) and re.search(r"\bjaskyn|\bpriepast|\blokalit", folded):
        add(0.5, "text: rozmery lokality")
    if photo_caption_lines and not map_caption_lines:
        score = min(score, 1.6)
        reasons.append("guard: foto popis bez mapového captionu")

    if re.search(r"\bplan\s+(?:prace|cinnosti|akcii|akcie|zasadnutia|vystavby|rozvoja|podujati|vyletu)\b", folded):
        score = min(score, 0.8)
        reasons.append("guard: administratívny plán")

    return round(score, 3), reasons


def likely_caption_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [
        line
        for line in lines
        if 3 <= len(line) <= 140
        and not re.fullmatch(r"\d+", line)
        and not re.match(r"^Spravodaj SSS\b|^Organizačné správy SSS\b", line, flags=re.I)
    ]


def is_map_caption(line: str) -> bool:
    if is_photo_caption(line):
        return False
    return bool(
        re.search(
            r"(?:^|[.!?:;,]\s+|\s{2,})"
            r"(?:Mapa|Mapka|Pôdorys|Podorys|[Pp]l[áa]n|[Rr]ez|[Pp]rierez|[Nn]áčrt|[Nn]acrt|[Pp]rofil)\b",
            line,
        )
    )


def is_photo_caption(line: str) -> bool:
    return bool(re.search(r"\bfoto(?:grafia)?\b|foto\s*:", fold_text(line)))


def visual_map_score(image_path: Path) -> tuple[float, list[str]]:
    try:
        import numpy as np
        from PIL import Image
    except Exception as exc:
        return 0.0, [f"visual unavailable: {exc}"]

    image = Image.open(image_path).convert("RGB")
    image.thumbnail((1000, 1000))
    arr = np.asarray(image, dtype=np.int16)
    if arr.size == 0:
        return 0.0, ["visual: empty"]

    gray = arr.mean(axis=2)
    white_ratio = float((gray > 238).mean())
    dark_ratio = float((gray < 85).mean())
    color_spread = np.abs(arr[:, :, 0] - arr[:, :, 1]) + np.abs(arr[:, :, 1] - arr[:, :, 2])
    color_ratio = float((color_spread > 35).mean())
    edge_ratio = float(((np.abs(np.diff(gray, axis=1)) > 40).mean() + (np.abs(np.diff(gray, axis=0)) > 40).mean()) / 2)

    score = 0.0
    if white_ratio >= 0.55:
        score += 0.22
    if 0.005 <= dark_ratio <= 0.22:
        score += 0.20
    if edge_ratio >= 0.035:
        score += 0.28
    if edge_ratio >= 0.060:
        score += 0.14
    if color_ratio <= 0.22:
        score += 0.12
    if white_ratio < 0.35 or color_ratio > 0.55:
        score = min(score, 0.45)

    reasons = [
        f"visual:white={white_ratio:.2f}",
        f"visual:dark={dark_ratio:.2f}",
        f"visual:color={color_ratio:.2f}",
        f"visual:edges={edge_ratio:.3f}",
    ]
    return round(min(1.0, score), 3), reasons


def erase_pdf_text_from_mask(mask: Any, layout: dict[str, Any], image_width: int, image_height: int) -> None:
    page_width = float(layout.get("width") or 0)
    page_height = float(layout.get("height") or 0)
    if page_width <= 0 or page_height <= 0:
        return
    scale_x = image_width / page_width
    scale_y = image_height / page_height
    for line in layout.get("lines") or []:
        try:
            x1 = max(0, int(float(line["xMin"]) * scale_x) - 5)
            y1 = max(0, int(float(line["yMin"]) * scale_y) - 4)
            x2 = min(image_width, int(float(line["xMax"]) * scale_x) + 5)
            y2 = min(image_height, int(float(line["yMax"]) * scale_y) + 4)
        except (KeyError, TypeError, ValueError):
            continue
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = False


def ocr_crop(crop_path: Path, languages: str, timeout: int) -> tuple[str, str | None]:
    if not languages:
        return "", "tesseract language unavailable"
    try:
        result = subprocess.run(
            ["tesseract", str(crop_path), "stdout", "-l", languages, "--psm", "6"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "", f"tesseract timeout after {timeout}s"
    if result.returncode != 0:
        return result.stdout.strip(), (result.stderr.strip() or "tesseract failed")
    return result.stdout.strip(), None


def score_ocr_map_terms(text: str) -> tuple[float, list[str]]:
    folded = fold_text(text)
    if not folded:
        return 0.0, ["ocr: empty"]
    reasons = []
    score = 0.0
    matches = sorted(set(match.group(0) for match in MAP_OCR_RE.finditer(folded)))
    if matches:
        score += min(3.0, len(matches) * 0.8)
        reasons.append("ocr: map terms " + ", ".join(matches[:8]))
    if re.search(r"\b(?:zameral\w*|kreslil\w*|mapoval\w*)\b", folded):
        score += 1.2
        reasons.append("ocr: zameral/kreslil/mapoval")
    if re.search(r"\b(?:mierka|meritko|1\s*[:/]\s*\d{2,5})\b", folded):
        score += 1.1
        reasons.append("ocr: mierka")
    if re.search(r"\b(?:podorys|plan|profil|rez|prierez|nacrt)\b", folded):
        score += 1.2
        reasons.append("ocr: technický typ")
    if PHOTO_OCR_RE.search(folded):
        score = min(score, 0.6)
        reasons.append("guard: OCR foto/snímka")
    if ADMIN_PLAN_RE.search(folded):
        score = min(score, 0.4)
        reasons.append("guard: administratívny plán")
    return round(score, 3), reasons


def object_visual_features(crop: Any) -> tuple[float, list[str], dict[str, float]]:
    try:
        import numpy as np
    except Exception as exc:
        return 0.0, [f"object-visual unavailable: {exc}"], {}

    arr = np.asarray(crop.convert("RGB"), dtype=np.int16)
    if arr.size == 0:
        return 0.0, ["object-visual: empty"], {}
    gray = arr.mean(axis=2)
    light_ratio = float((gray > 225).mean())
    very_light_ratio = float((gray > 242).mean())
    dark_ratio = float((gray < 105).mean())
    midtone_ratio = float(((gray >= 105) & (gray <= 225)).mean())
    color_spread = np.abs(arr[:, :, 0] - arr[:, :, 1]) + np.abs(arr[:, :, 1] - arr[:, :, 2])
    color_ratio = float((color_spread > 34).mean())
    edge_ratio = float(
        (
            (np.abs(np.diff(gray, axis=1)) > 38).mean()
            + (np.abs(np.diff(gray, axis=0)) > 38).mean()
        )
        / 2
    )

    score = 0.0
    if light_ratio >= 0.58:
        score += 0.25
    if very_light_ratio >= 0.42:
        score += 0.14
    if 0.006 <= dark_ratio <= 0.22:
        score += 0.20
    if color_ratio <= 0.18:
        score += 0.18
    if midtone_ratio <= 0.34:
        score += 0.16
    if edge_ratio >= 0.020:
        score += 0.16
    if light_ratio < 0.48 or color_ratio > 0.32 or midtone_ratio > 0.50:
        score = min(score, 0.45)
    if dark_ratio > 0.30:
        score = min(score, 0.55)

    features = {
        "light": light_ratio,
        "very_light": very_light_ratio,
        "dark": dark_ratio,
        "midtone": midtone_ratio,
        "color": color_ratio,
        "edges": edge_ratio,
    }
    reasons = [
        f"object-visual:light={light_ratio:.2f}",
        f"object-visual:dark={dark_ratio:.2f}",
        f"object-visual:midtone={midtone_ratio:.2f}",
        f"object-visual:color={color_ratio:.2f}",
        f"object-visual:edges={edge_ratio:.3f}",
    ]
    return round(min(1.0, score), 3), reasons, features


def ocr_object_candidates(
    image_path: Path,
    layout: dict[str, Any],
    crop_dir: Path,
    ocr_languages: str,
    ocr_timeout: int,
) -> list[dict[str, Any]]:
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
    except Exception as exc:
        return [
            {
                "candidate": False,
                "reason": f"ocr-object unavailable: {exc}",
            }
        ]

    if not ocr_languages:
        return [{"candidate": False, "reason": "ocr-object skipped: no installed OCR language"}]

    image = Image.open(image_path).convert("RGB")
    image_width, image_height = image.size
    if image_width <= 0 or image_height <= 0:
        return []
    arr = np.asarray(image, dtype=np.int16)
    gray = arr.mean(axis=2)
    mask = gray < 246
    erase_pdf_text_from_mask(mask, layout, image_width, image_height)

    # Tighten the page mask: ignore margins/footers where logos and page furniture live.
    margin_x = int(image_width * 0.035)
    margin_y = int(image_height * 0.035)
    mask[:margin_y, :] = False
    mask[-margin_y:, :] = False
    mask[:, :margin_x] = False
    mask[:, -margin_x:] = False

    mask = ndimage.binary_dilation(mask, iterations=5)
    labels, count = ndimage.label(mask)
    slices = ndimage.find_objects(labels)
    crop_dir.mkdir(parents=True, exist_ok=True)
    page_area = image_width * image_height
    page_width = float(layout.get("width") or 0)
    page_height = float(layout.get("height") or 0)
    scale_x = image_width / page_width if page_width > 0 else 1.0
    scale_y = image_height / page_height if page_height > 0 else 1.0

    records = []
    for label_index, component_slice in enumerate(slices, start=1):
        if component_slice is None:
            continue
        y_slice, x_slice = component_slice
        x1, x2 = x_slice.start, x_slice.stop
        y1, y2 = y_slice.start, y_slice.stop
        width = x2 - x1
        height = y2 - y1
        area_ratio = (width * height) / max(1, page_area)
        if width < image_width * 0.18 or height < image_height * 0.08 or area_ratio < 0.025:
            continue
        if width > image_width * 0.96 and height > image_height * 0.92:
            continue

        pad = 8
        crop_box = (
            max(0, x1 - pad),
            max(0, y1 - pad),
            min(image_width, x2 + pad),
            min(image_height, y2 + pad),
        )
        crop = image.crop(crop_box)
        visual_score, visual_reasons, features = object_visual_features(crop)
        if visual_score < 0.72:
            continue

        crop_path = crop_dir / f"{image_path.stem}_obj{label_index}.png"
        crop.save(crop_path)
        ocr_text, ocr_error = ocr_crop(crop_path, ocr_languages, ocr_timeout)
        ocr_score, ocr_reasons = score_ocr_map_terms(ocr_text)
        candidate = visual_score >= 0.72 and ocr_score >= 2.4 and not ocr_error
        if PHOTO_OCR_RE.search(fold_text(ocr_text)):
            candidate = False

        records.append(
            {
                "candidate": candidate,
                "source": "ocr_object_without_caption",
                "bbox_image": {"xMin": x1, "yMin": y1, "xMax": x2, "yMax": y2},
                "bbox": {
                    "xMin": round(x1 / scale_x, 3),
                    "yMin": round(y1 / scale_y, 3),
                    "xMax": round(x2 / scale_x, 3),
                    "yMax": round(y2 / scale_y, 3),
                },
                "crop_path": relative(crop_path),
                "visual_score": visual_score,
                "ocr_score": ocr_score,
                "score": round((visual_score + min(1.0, ocr_score / 4.0)) / 2, 3),
                "features": features,
                "reasons": visual_reasons + ocr_reasons + ([f"ocr_error: {ocr_error}"] if ocr_error else []),
                "ocr_text": re.sub(r"\s+", " ", ocr_text).strip()[:800],
                "ocr_languages": ocr_languages,
            }
        )

    records.sort(key=lambda item: (not item.get("candidate"), -float(item.get("score") or 0)))
    return records[:6]


def caption_object_score(
    image_path: Path,
    page_width: float,
    page_height: float,
    caption_bbox: dict[str, float],
) -> tuple[float, list[str]]:
    try:
        import numpy as np
        from PIL import Image
    except Exception as exc:
        return 0.0, [f"caption-object unavailable: {exc}"]

    if page_width <= 0 or page_height <= 0:
        return 0.0, ["caption-object: missing page bbox"]

    cap_x1 = float(caption_bbox["xMin"])
    cap_y1 = float(caption_bbox["yMin"])
    cap_x2 = float(caption_bbox["xMax"])
    cap_w = max(1.0, cap_x2 - cap_x1)

    search_y2 = cap_y1 - 3.0
    search_y1 = max(18.0, cap_y1 - 390.0)
    if search_y2 - search_y1 < 45.0:
        return 0.0, ["caption-object: no usable area above caption"]

    search_x1 = max(20.0, cap_x1 - max(35.0, cap_w * 0.8))
    search_x2 = min(page_width - 20.0, cap_x2 + max(120.0, min(235.0, cap_w * 2.6)))
    if search_x2 - search_x1 < 90.0:
        return 0.0, ["caption-object: search area too narrow"]

    image = Image.open(image_path).convert("RGB")
    scale_x = image.width / page_width
    scale_y = image.height / page_height
    crop_box = (
        max(0, int(search_x1 * scale_x)),
        max(0, int(search_y1 * scale_y)),
        min(image.width, int(search_x2 * scale_x)),
        min(image.height, int(search_y2 * scale_y)),
    )
    if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
        return 0.0, ["caption-object: empty crop"]

    arr = np.asarray(image.crop(crop_box), dtype=np.int16)
    gray = arr.mean(axis=2)
    mask = gray < 245
    if not mask.any():
        return 0.0, ["caption-object: no non-white object above"]

    ys, xs = np.where(mask)
    crop_h, crop_w = mask.shape
    bbox_w = float(xs.max() - xs.min() + 1) / max(1, crop_w)
    bbox_h = float(ys.max() - ys.min() + 1) / max(1, crop_h)
    ink_ratio = float(mask.mean())
    row_coverage = float((mask.mean(axis=1) > 0.006).mean())
    col_coverage = float((mask.mean(axis=0) > 0.006).mean())
    edge_ratio = float(
        (
            (np.abs(np.diff(gray, axis=1)) > 38).mean()
            + (np.abs(np.diff(gray, axis=0)) > 38).mean()
        )
        / 2
    )

    score = 0.0
    if bbox_w >= 0.45:
        score += 0.25
    if bbox_h >= 0.35:
        score += 0.25
    if row_coverage >= 0.24:
        score += 0.18
    if col_coverage >= 0.24:
        score += 0.18
    if edge_ratio >= 0.018:
        score += 0.14
    if ink_ratio < 0.010:
        score = min(score, 0.35)

    reasons = [
        f"caption-object:ink={ink_ratio:.3f}",
        f"caption-object:bbox={bbox_w:.2f}x{bbox_h:.2f}",
        f"caption-object:rows={row_coverage:.2f}",
        f"caption-object:cols={col_coverage:.2f}",
        f"caption-object:edges={edge_ratio:.3f}",
    ]
    return round(min(1.0, score), 3), reasons


def article_heading_y(layout: dict[str, Any], article: dict[str, Any]) -> float | None:
    title = fold_text(article.get("title") or "")
    if not title:
        return None
    title_parts = [title]
    if " - " in str(article.get("title") or ""):
        title_parts.append(fold_text(str(article.get("title")).split(" - ", 1)[0]))
    for line in layout.get("lines") or []:
        folded_line = fold_text(line.get("text") or "")
        if any(part and (part in folded_line or folded_line in part) for part in title_parts):
            try:
                return float(line["yMin"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def articles_for_printed_page(
    printed_page: int,
    articles: list[dict[str, Any]],
    layout: dict[str, Any] | None = None,
    caption_y: float | None = None,
) -> list[dict[str, Any]]:
    """Best-effort section assignment for grouped reports with start pages only."""
    starts = []
    for article in articles:
        start = article.get("page_start") or article.get("pdf_page_start")
        try:
            starts.append((int(start), article))
        except (TypeError, ValueError):
            continue
    starts.sort(key=lambda item: item[0])
    matches = []
    for index, (start, article) in enumerate(starts):
        next_start = starts[index + 1][0] if index + 1 < len(starts) else 10_000
        if start <= printed_page < next_start:
            if layout and caption_y is not None and start == printed_page and index > 0:
                heading_y = article_heading_y(layout, article)
                if heading_y is not None and caption_y < heading_y - 8:
                    matches.append(starts[index - 1][1])
                    break
            matches.append(article)
            break
    return matches


def article_payload(article: dict[str, Any], printed_page: int | None = None) -> dict[str, Any]:
    return {
        "id": article.get("id"),
        "title": article.get("title"),
        "pages": article.get("pages"),
        "page_start": article.get("page_start"),
        "pdf_page_start": article.get("pdf_page_start"),
        "pdf_page_end": article.get("pdf_page_end"),
        "matched_printed_page": printed_page,
    }


def build_prefilter_record(
    pdf_path: Path,
    page: int,
    render_dir: Path,
    articles: list[dict[str, Any]],
    dpi: int,
    printed_page_offset: int,
    enable_ocr_objects: bool,
    ocr_languages: str,
    ocr_timeout: int,
) -> dict[str, Any]:
    text = pdftotext_page(pdf_path, page)
    text_score, text_reasons = text_map_score(text)
    image_path = render_pdf_page(pdf_path, page, render_dir, dpi)
    visual_score, visual_reasons = visual_map_score(image_path)
    bbox_layout, caption_candidates = map_caption_candidates(pdf_path, page)
    caption_matches = []
    for caption in caption_candidates:
        object_score, object_reasons = caption_object_score(
            image_path,
            float(bbox_layout["width"] or 0),
            float(bbox_layout["height"] or 0),
            caption["bbox"],
        )
        caption_matches.append(
            {
                "text": caption["text"],
                "line_text": caption["line_text"],
                "bbox": caption["bbox"],
                "object_score": object_score,
                "object_reasons": object_reasons,
                "object_above": object_score >= 0.55,
            }
        )
    printed_page = page - printed_page_offset
    has_caption_object = any(match["object_above"] for match in caption_matches)
    ocr_object_matches = []
    if enable_ocr_objects and not has_caption_object:
        ocr_object_matches = ocr_object_candidates(
            image_path,
            bbox_layout,
            render_dir / "ocr_objects",
            ocr_languages,
            ocr_timeout,
        )
    has_ocr_object = any(match.get("candidate") for match in ocr_object_matches)
    primary_caption_y = min(
        (float(match["bbox"]["yMin"]) for match in caption_matches if match["object_above"]),
        default=None,
    )
    primary_object_y = min(
        (float(match["bbox"]["yMin"]) for match in ocr_object_matches if match.get("candidate")),
        default=None,
    )
    primary_marker_y = primary_caption_y if primary_caption_y is not None else primary_object_y
    article_matches = [
        article_payload(article, printed_page)
        for article in articles_for_printed_page(printed_page, articles, bbox_layout, primary_marker_y)
    ]
    caption_reasons = [
        f"caption-object: {match['text']}"
        for match in caption_matches
        if match["object_above"]
    ]
    ocr_reasons = [
        "ocr-object: " + "; ".join(match.get("reasons") or [])[:180]
        for match in ocr_object_matches
        if match.get("candidate")
    ]
    candidate_sources = []
    if has_caption_object:
        candidate_sources.append("caption_object")
    if has_ocr_object:
        candidate_sources.append("ocr_object_without_caption")
    candidate = bool(candidate_sources)
    ocr_object_score = max((float(match.get("score") or 0) for match in ocr_object_matches), default=0.0)
    return {
        "created_at": utc_now(),
        "page": page,
        "printed_page_guess": printed_page,
        "candidate": candidate,
        "candidate_sources": candidate_sources,
        "text_score": text_score,
        "visual_score": visual_score,
        "score": round(max(text_score / 4.0, visual_score, ocr_object_score), 3),
        "reasons": text_reasons + caption_reasons + ocr_reasons + visual_reasons,
        "caption_matches": caption_matches,
        "ocr_object_matches": ocr_object_matches,
        "image_path": relative(image_path),
        "articles": article_matches,
        "text_excerpt": re.sub(r"\s+", " ", text).strip()[:700],
    }


def build_summary(
    args: argparse.Namespace,
    pdf_path: Path,
    pdf_url: str,
    pdf_pages: int,
    prefilter_records: list[dict[str, Any]],
    confirmed_records: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = [record for record in prefilter_records if record["candidate"]]
    confirmed = [record for record in confirmed_records if record.get("ai", {}).get("map_plan") is True]
    ocr_candidates = [
        record
        for record in candidates
        if "ocr_object_without_caption" in (record.get("candidate_sources") or [])
    ]
    return {
        "created_at": utc_now(),
        "detection_mode": "hybrid_prefilter_plus_vision_confirmation",
        "model": None if args.no_ai else args.model,
        "year": args.year,
        "issue": args.issue,
        "pdf_url": pdf_url,
        "pdf_path": relative(pdf_path),
        "pdf_pages": pdf_pages,
        "ignored_first_pages": args.ignore_first_pages if not args.include_cover_pages else 0,
        "ignored_last_pages": args.ignore_last_pages if not args.include_cover_pages else 0,
        "ocr_objects_enabled": not args.disable_ocr_objects,
        "ocr_languages_requested": args.ocr_languages,
        "ocr_languages_used": getattr(args, "resolved_ocr_languages", ""),
        "processed_page_count": len(prefilter_records),
        "candidate_pages": [record["page"] for record in candidates],
        "candidate_page_count": len(candidates),
        "ocr_object_candidate_pages": [record["page"] for record in ocr_candidates],
        "ocr_object_candidate_page_count": len(ocr_candidates),
        "confirmed_pages": [record["page"] for record in confirmed],
        "confirmed_page_count": len(confirmed),
        "confirmed_records": confirmed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--issue", default="1")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--dpi", type=int, default=130)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--pages", help="Comma-separated physical PDF pages.")
    parser.add_argument("--page-start", type=int)
    parser.add_argument("--page-end", type=int)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--ignore-first-pages", type=int, default=2)
    parser.add_argument("--ignore-last-pages", type=int, default=4)
    parser.add_argument("--include-cover-pages", action="store_true")
    parser.add_argument("--printed-page-offset", type=int, default=2)
    parser.add_argument("--ocr-languages", default=DEFAULT_OCR_LANGUAGES)
    parser.add_argument("--ocr-timeout", type=int, default=30)
    parser.add_argument("--disable-ocr-objects", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--reuse-prefilter", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-suffix", default="hybrid")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.issue = str(args.issue).strip()
    articles = load_issue_articles(args.year, args.issue)
    fulltext_records = load_issue_fulltext(args.year, args.issue)
    pdf_path, pdf_url = resolve_pdf_path(fulltext_records, articles)
    pdf_pages = pdf_page_count(pdf_path)
    args.resolved_ocr_languages = "" if args.disable_ocr_objects else resolve_ocr_languages(args.ocr_languages)

    suffix = f"_{args.output_suffix.strip('_')}" if args.output_suffix else ""
    slug = f"{args.year}_{args.issue}{suffix}"
    render_dir = OUTPUT_DIR / "rendered" / slug
    prefilter_path = OUTPUT_DIR / f"map_prefilter_{slug}.jsonl"
    confirmed_path = OUTPUT_DIR / f"map_confirmed_{slug}.jsonl"
    summary_path = OUTPUT_DIR / f"map_hybrid_{slug}_summary.json"

    pages = selected_pages(pdf_pages, args)
    if args.reuse_prefilter:
        existing_prefilter_records = load_jsonl(prefilter_path)
        if not existing_prefilter_records:
            raise RuntimeError(f"Cannot reuse missing or empty prefilter: {relative(prefilter_path)}")
        page_set = set(pages) if args.pages else None
        prefilter_records = [
            record for record in existing_prefilter_records
            if page_set is None or int(record["page"]) in page_set
        ]
    else:
        prefilter_records = [] if args.force else load_jsonl(prefilter_path)
        prefilter_by_page = {int(record["page"]): record for record in prefilter_records}
        for page in pages:
            if page in prefilter_by_page and not args.force:
                if args.progress:
                    print(f"prefilter page={page} skip cached", flush=True)
                continue
            record = build_prefilter_record(
                pdf_path,
                page,
                render_dir,
                articles,
                args.dpi,
                args.printed_page_offset,
                not args.disable_ocr_objects,
                args.resolved_ocr_languages,
                args.ocr_timeout,
            )
            prefilter_by_page[page] = record
            prefilter_records = list(prefilter_by_page.values())
            write_jsonl(prefilter_path, prefilter_records)
            if args.progress:
                sources = ",".join(record.get("candidate_sources") or [])
                ocr_hits = sum(1 for item in record.get("ocr_object_matches") or [] if item.get("candidate"))
                print(
                    f"prefilter page={page} candidate={record['candidate']} "
                    f"sources={sources or '-'} ocr_hits={ocr_hits}",
                    flush=True,
                )
        write_jsonl(prefilter_path, prefilter_records)
    candidates = [record for record in prefilter_records if record["candidate"]]
    print("candidate_pages=" + ",".join(str(record["page"]) for record in candidates))

    confirmed_records: list[dict[str, Any]] = [] if args.force else load_jsonl(confirmed_path)
    confirmed_by_page = {int(record["page"]): record for record in confirmed_records}
    if not args.no_ai:
        for record in candidates:
            page = int(record["page"])
            if page in confirmed_by_page and not args.force:
                print(f"skip page={page} confirmed", flush=True)
                continue
            image_path = BASE_DIR / record["image_path"]
            ai = classify_image(image_path, args.model, args.timeout, args.ollama_url)
            confirmed = {
                "created_at": utc_now(),
                "detection_mode": "hybrid_prefilter_plus_vision_confirmation",
                "model": args.model,
                "year": args.year,
                "issue": args.issue,
                "page": record["page"],
                "printed_page_guess": record["printed_page_guess"],
                "prefilter": {
                    "text_score": record["text_score"],
                    "visual_score": record["visual_score"],
                    "reasons": record["reasons"],
                    "candidate_sources": record.get("candidate_sources") or [],
                },
                "image_path": record["image_path"],
                "articles": record["articles"],
                "caption_matches": record.get("caption_matches") or [],
                "ocr_object_matches": record.get("ocr_object_matches") or [],
                "ai": ai,
            }
            confirmed_by_page[page] = confirmed
            confirmed_records = list(confirmed_by_page.values())
            write_jsonl(confirmed_path, confirmed_records)
            print(
                f"page={record['page']} ai_map={ai['map_plan']} confidence={ai['confidence']} "
                f"kind={ai['kind']} articles={','.join(str(a['id']) for a in record['articles']) or '-'}",
                flush=True,
            )
    else:
        write_jsonl(confirmed_path, confirmed_records)

    write_json(summary_path, build_summary(args, pdf_path, pdf_url, pdf_pages, prefilter_records, confirmed_records))
    print(f"prefilter={relative(prefilter_path)}")
    print(f"confirmed={relative(confirmed_path)}")
    print(f"summary={relative(summary_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
