from __future__ import annotations

from app.ai.matching.explainability_evaluator import (
    _f1,
    _precision,
    _recall,
    _validate_dataset,
    load_golden_dataset,
)


def test_precision_zero_denominator_rules() -> None:
    assert _precision(0, 0, 0) == 1.0
    assert _precision(0, 0, 1) == 0.0
    assert _precision(2, 1, 0) == 2 / 3


def test_recall_zero_denominator_rule() -> None:
    assert _recall(0, 0) == 1.0
    assert _recall(2, 2) == 0.5


def test_f1_zero_denominator_rule() -> None:
    assert _f1(0.0, 0.0) == 0.0
    assert _f1(1.0, 0.5) == 2 / 3


def test_golden_dataset_passes_strict_fixture_validation() -> None:
    assert _validate_dataset(load_golden_dataset()) == []


def test_fixture_validation_rejects_fabricated_expected_quote() -> None:
    dataset = load_golden_dataset()
    dataset["scenarios"][0]["ground_truth"]["skills_ground_truth"]["Python"][
        "expected_evidence_spans"
    ][0]["quote"] = "This quote does not exist"

    errors = _validate_dataset(dataset)

    assert any("not present in section" in error for error in errors)
