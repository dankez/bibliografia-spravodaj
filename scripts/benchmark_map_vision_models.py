#!/usr/bin/env python3
"""Benchmark Ollama vision models on a fixed SSS map/non-map page sample."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
from pathlib import Path
from statistics import median
from typing import Any

from ai_detect_pdf_maps import BASE_DIR, OUTPUT_DIR, classify_image, render_pdf_page, write_json, write_jsonl


GROUND_TRUTH = OUTPUT_DIR / "ground_truth_2026_1.json"
DEFAULT_SAMPLE_PAGES = [
    1,
    2,
    3,
    10,
    16,
    17,
    18,
    25,
    42,
    58,
    59,
    60,
    63,
    64,
    65,
    75,
    90,
    91,
    92,
    102,
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_pages(value: str | None) -> list[int]:
    if not value:
        return DEFAULT_SAMPLE_PAGES
    pages = []
    for item in value.split(","):
        item = item.strip()
        if item:
            pages.append(int(item))
    return list(dict.fromkeys(pages))


def model_slug(model: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", model.strip())
    return slug.strip("_") or "model"


def metric_summary(rows: list[dict[str, Any]], positive_pages: set[int]) -> dict[str, Any]:
    processed = {int(row["page"]) for row in rows}
    predicted = {int(row["page"]) for row in rows if row.get("prediction") is True}
    truth = processed & positive_pages
    tp = predicted & positive_pages
    fp = predicted - positive_pages
    fn = truth - predicted
    tn = processed - predicted - positive_pages
    latencies = [float(row["latency_seconds"]) for row in rows if row.get("latency_seconds") is not None]
    parse_errors = [row for row in rows if (row.get("ai") or {}).get("parse_error")]
    precision = len(tp) / len(predicted) if predicted else None
    recall = len(tp) / len(truth) if truth else None
    accuracy = (len(tp) + len(tn)) / len(processed) if processed else None
    return {
        "processed_page_count": len(processed),
        "truth_positive_pages": sorted(truth),
        "predicted_positive_pages": sorted(predicted),
        "true_positive": sorted(tp),
        "false_positive": sorted(fp),
        "false_negative": sorted(fn),
        "true_negative_count": len(tn),
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy,
        "parse_error_count": len(parse_errors),
        "latency_total_seconds": round(sum(latencies), 3) if latencies else None,
        "latency_avg_seconds": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "latency_median_seconds": round(median(latencies), 3) if latencies else None,
    }


def run_model(
    model: str,
    pdf_path: Path,
    pdf_url: str,
    pages: list[int],
    positive_pages: set[int],
    args: argparse.Namespace,
) -> dict[str, Any]:
    slug = f"benchmark_{model_slug(model)}_{args.output_suffix}"
    render_dir = OUTPUT_DIR / "rendered" / slug
    output_path = OUTPUT_DIR / f"model_benchmark_{model_slug(model)}_{args.output_suffix}.jsonl"
    summary_path = OUTPUT_DIR / f"model_benchmark_{model_slug(model)}_{args.output_suffix}_summary.json"
    rows: list[dict[str, Any]] = []

    print(f"\nMODEL {model}")
    print(f"output={output_path.relative_to(BASE_DIR)}")
    for index, page in enumerate(pages, start=1):
        image_path = render_pdf_page(pdf_path, page, render_dir, args.dpi)
        started = time.perf_counter()
        ai = classify_image(image_path, model, args.timeout, args.ollama_url)
        latency = time.perf_counter() - started
        prediction = bool(ai.get("map_plan"))
        truth = page in positive_pages
        row = {
            "created_at": utc_now(),
            "model": model,
            "year": args.year,
            "issue": args.issue,
            "pdf_url": pdf_url,
            "pdf_path": str(pdf_path.relative_to(BASE_DIR)),
            "page": page,
            "truth": truth,
            "prediction": prediction,
            "correct": truth == prediction,
            "latency_seconds": round(latency, 3),
            "image_path": str(image_path.relative_to(BASE_DIR)),
            "ai": ai,
        }
        rows.append(row)
        write_jsonl(output_path, rows)
        status = "OK" if row["correct"] else "MISS"
        print(
            f"[{index:02d}/{len(pages)}] page={page:>3} truth={truth!s:<5} "
            f"pred={prediction!s:<5} {status:<4} {latency:6.2f}s "
            f"{ai.get('confidence', '-')}/{ai.get('kind', '-')}",
            flush=True,
        )

    summary = {
        "created_at": utc_now(),
        "model": model,
        "year": args.year,
        "issue": args.issue,
        "pdf_url": pdf_url,
        "pdf_path": str(pdf_path.relative_to(BASE_DIR)),
        "dpi": args.dpi,
        "timeout": args.timeout,
        "pages": pages,
        **metric_summary(rows, positive_pages),
        "output": str(output_path.relative_to(BASE_DIR)),
    }
    write_json(summary_path, summary)
    print(f"summary={summary_path.relative_to(BASE_DIR)}")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, default=GROUND_TRUTH)
    parser.add_argument("--models", required=True, help="Comma-separated Ollama models.")
    parser.add_argument("--pages", help="Comma-separated physical PDF pages.")
    parser.add_argument("--dpi", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--output-suffix", default="2026_1_sample20")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--issue", default="1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ground_truth = read_json(args.ground_truth)
    pdf_path = BASE_DIR / str(ground_truth["pdf_cache"])
    pdf_url = str(ground_truth.get("pdf_url") or "")
    positive_pages = {int(page) for page in ground_truth["positive_map_plan_pages"]}
    pages = parse_pages(args.pages)
    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models:
        raise RuntimeError("--models did not contain any model name")

    summaries = []
    for model in models:
        summaries.append(run_model(model, pdf_path, pdf_url, pages, positive_pages, args))

    comparison_path = OUTPUT_DIR / f"model_benchmark_comparison_{args.output_suffix}.json"
    write_json(
        comparison_path,
        {
            "created_at": utc_now(),
            "ground_truth": str(args.ground_truth.relative_to(BASE_DIR)),
            "pages": pages,
            "positive_pages": sorted(positive_pages & set(pages)),
            "summaries": summaries,
        },
    )
    print("\nCOMPARISON")
    for summary in summaries:
        print(
            (
                "{model}: acc={acc} precision={precision} recall={recall} "
                "avg={avg}s total={total}s parse_errors={parse_errors} fp={fp} fn={fn}"
            ).format(
                model=summary["model"],
                acc=fmt_metric(summary["accuracy"]),
                precision=fmt_metric(summary["precision"]),
                recall=fmt_metric(summary["recall"]),
                avg=summary["latency_avg_seconds"],
                total=summary["latency_total_seconds"],
                parse_errors=summary["parse_error_count"],
                fp=summary["false_positive"],
                fn=summary["false_negative"],
            )
        )
    print(f"comparison={comparison_path.relative_to(BASE_DIR)}")
    return 0


def fmt_metric(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
