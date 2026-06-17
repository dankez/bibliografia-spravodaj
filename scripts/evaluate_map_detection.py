#!/usr/bin/env python3
"""Evaluate map/plan detection JSONL against manual page-level ground truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_GROUND_TRUTH = BASE_DIR / "data" / "ai_map_detection" / "ground_truth_2026_1.json"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path}:{line_number}: {exc}") from exc


def as_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("detections", help="Detection JSONL, e.g. data/ai_map_detection/ai_maps_2026_1_smoke2.jsonl")
    parser.add_argument("--ground-truth", default=str(DEFAULT_GROUND_TRUTH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    detection_path = as_path(args.detections)
    ground_truth_path = as_path(args.ground_truth)
    ground_truth = read_json(ground_truth_path)
    truth_positive = {int(page) for page in ground_truth["positive_map_plan_pages"]}
    rows = list(iter_jsonl(detection_path))
    processed = {int(row["page"]) for row in rows}
    predicted_positive = {
        int(row["page"])
        for row in rows
        if (row.get("ai") or row).get("map_plan") is True
    }

    truth_in_processed = truth_positive & processed
    true_positive = predicted_positive & truth_positive
    false_positive = predicted_positive - truth_positive
    false_negative = truth_in_processed - predicted_positive
    true_negative = processed - predicted_positive - truth_positive

    precision = len(true_positive) / len(predicted_positive) if predicted_positive else None
    recall = len(true_positive) / len(truth_in_processed) if truth_in_processed else None
    result = {
        "detections": str(detection_path.relative_to(BASE_DIR)),
        "ground_truth": str(ground_truth_path.relative_to(BASE_DIR)),
        "processed_pages": sorted(processed),
        "truth_positive_pages": sorted(truth_positive),
        "predicted_positive_pages": sorted(predicted_positive),
        "true_positive": sorted(true_positive),
        "false_positive": sorted(false_positive),
        "false_negative_in_processed_pages": sorted(false_negative),
        "true_negative_in_processed_pages": sorted(true_negative),
        "precision_on_processed_pages": precision,
        "recall_on_processed_truth_pages": recall,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
