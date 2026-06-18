import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark_map_vision_models as benchmark


def test_parse_pages_deduplicates_and_preserves_order():
    assert benchmark.parse_pages("17, 59,17, 64") == [17, 59, 64]


def test_parse_pages_uses_default_sample_when_empty():
    assert benchmark.parse_pages(None) == benchmark.DEFAULT_SAMPLE_PAGES


def test_model_slug_keeps_filename_safe_model_name():
    assert benchmark.model_slug("gemma4:e2b-it-qat") == "gemma4_e2b-it-qat"


def test_metric_summary_counts_accuracy_and_speed():
    rows = [
        {"page": 17, "prediction": True, "latency_seconds": 2.0, "ai": {}},
        {"page": 18, "prediction": True, "latency_seconds": 4.0, "ai": {}},
        {"page": 59, "prediction": False, "latency_seconds": 6.0, "ai": {"parse_error": "bad_json"}},
        {"page": 60, "prediction": False, "latency_seconds": 8.0, "ai": {}},
    ]

    summary = benchmark.metric_summary(rows, {17, 59})

    assert summary["true_positive"] == [17]
    assert summary["false_positive"] == [18]
    assert summary["false_negative"] == [59]
    assert summary["true_negative_count"] == 1
    assert summary["precision"] == 0.5
    assert summary["recall"] == 0.5
    assert summary["accuracy"] == 0.5
    assert summary["parse_error_count"] == 1
    assert summary["latency_total_seconds"] == 20.0
    assert summary["latency_avg_seconds"] == 5.0
    assert summary["latency_median_seconds"] == 5.0
