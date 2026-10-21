from __future__ import annotations

from app.ai.matching.explainability_evaluator import (
    CANONICAL_STATUSES,
    DEFAULT_DATASET_PATH,
    evaluate_dataset,
    load_golden_dataset,
)

THRESHOLDS = {
    "min_evidence_recall": 0.90,
    "min_micro_f1": 0.90,
    "min_macro_f1": 0.90,
    "min_inquiry_precision": 0.95,
    "min_inquiry_recall": 0.95,
}


async def test_explainability_benchmark_gate() -> None:
    dataset = load_golden_dataset()
    report = await evaluate_dataset(dataset)

    assert report.scenario_count == 20
    assert report.skill_count > 0
    assert set(report.class_metrics) == set(CANONICAL_STATUSES)
    assert all(
        metrics.true_positives + metrics.false_negatives > 0
        for metrics in report.class_metrics.values()
    ), "the dataset must exercise every canonical skill status"

    assert report.quote_integrity_precision == 1.0
    assert report.evidence_recall >= 0.90
    assert report.micro_f1 >= 0.90
    assert report.macro_f1 >= 0.90
    assert report.post_fallback_contradiction_rate == 0.0
    assert report.raw_contradiction_count > 0, (
        "the benchmark must exercise contradiction fallback"
    )
    assert report.inquiry_precision >= 0.95
    assert report.inquiry_recall >= 0.95
    assert report.errors == []
    assert report.passes(**THRESHOLDS), report.errors


def test_dataset_is_the_repository_golden_file() -> None:
    dataset = load_golden_dataset()

    assert DEFAULT_DATASET_PATH.name == "explainability_golden_dataset.json"
    assert dataset["metadata"]["reference_date"] == "2026-10-01"
    assert len(dataset["metadata"]["categories"]) == 20
    assert len(dataset["scenarios"]) == 20
