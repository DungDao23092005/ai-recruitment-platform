"""Deterministic offline benchmark for Explainable AI explanations.

The evaluator loads the golden dataset, validates every fixture against the
production schemas, runs ``MatchExplanationService`` with an in-memory narrative
double (never a real provider), and computes:

* multi-class skill classification precision/recall/F1, micro-F1 and macro-F1,
  including the specified zero-denominator rules;
* verbatim quote integrity and semantic evidence-span recall;
* raw versus post-fallback score contradictions;
* areas-for-inquiry precision/recall; and
* sample-validity errors that must never be hidden by aggregate metrics.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.ai.matching.evidence_verifier import EvidenceVerifier
from app.schemas.ai_explanation import (
    ApplicationMatchExplanationResponse,
    EvidenceExcerpt,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema
from app.services.match_explanation_service import (
    MatchExplanationService,
    _narrative_contradicts_score,
)

REFERENCE_DATE = date(2026, 10, 1)
CANONICAL_STATUSES = (
    "matched_evidenced",
    "partially_matched",
    "not_evidenced_in_cv",
    "insufficient_data",
)
DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "evaluation"
    / "explainability_golden_dataset.json"
)


@dataclass(frozen=True)
class ClassMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True)
class EvaluationReport:
    scenario_count: int
    skill_count: int
    class_metrics: dict[str, ClassMetrics]
    micro_f1: float
    macro_f1: float
    quote_integrity_precision: float
    total_excerpts: int
    evidence_recall: float
    expected_span_count: int
    matched_span_count: int
    inquiry_precision: float
    inquiry_recall: float
    retrieved_inquiry_count: int
    expected_inquiry_count: int
    raw_contradiction_rate: float
    raw_contradiction_count: int
    post_fallback_contradiction_rate: float
    post_fallback_contradiction_count: int
    errors: list[str] = field(default_factory=list)

    def passes(
        self,
        *,
        min_evidence_recall: float = 0.90,
        min_micro_f1: float = 0.90,
        min_macro_f1: float = 0.90,
        min_inquiry_precision: float = 0.95,
        min_inquiry_recall: float = 0.95,
    ) -> bool:
        return (
            not self.errors
            and self.quote_integrity_precision == 1.0
            and self.evidence_recall >= min_evidence_recall
            and self.micro_f1 >= min_micro_f1
            and self.macro_f1 >= min_macro_f1
            and self.post_fallback_contradiction_rate == 0.0
            and self.inquiry_precision >= min_inquiry_precision
            and self.inquiry_recall >= min_inquiry_recall
        )


@dataclass
class _Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0


@dataclass
class _ScenarioNarrative:
    summary: str
    match_score: float
    model_name: str = "gemini-3.5-flash-lite"

    def __post_init__(self) -> None:
        self.llm_provider = SimpleNamespace(model_name=self.model_name)

    async def explain_match(self, **_kwargs):
        return SimpleNamespace(
            summary=self.summary,
            match_score=self.match_score,
        )


def load_golden_dataset(
    path: str | Path | None = None,
) -> dict:
    dataset_path = Path(path) if path is not None else DEFAULT_DATASET_PATH
    with dataset_path.open("r", encoding="utf-8") as handle:
        dataset = json.load(handle)
    if not isinstance(dataset, dict):
        raise ValueError("golden dataset must be a JSON object")
    return dataset


def _validate_dataset(dataset: dict) -> list[str]:
    errors: list[str] = []
    metadata = dataset.get("metadata")
    scenarios = dataset.get("scenarios")
    if not isinstance(metadata, dict):
        return ["metadata must be an object"]
    if metadata.get("reference_date") != REFERENCE_DATE.isoformat():
        errors.append(
            "metadata.reference_date must be "
            f"{REFERENCE_DATE.isoformat()!r}"
        )
    categories = metadata.get("categories")
    if not isinstance(categories, list) or len(categories) != 20:
        errors.append("metadata.categories must contain exactly 20 entries")
    if not isinstance(scenarios, list) or len(scenarios) != 20:
        errors.append("dataset must contain exactly 20 scenarios")
        return errors

    verifier = EvidenceVerifier()
    seen_ids: set[str] = set()
    seen_categories: set[str] = set()
    for index, scenario in enumerate(scenarios):
        label = f"scenarios[{index}]"
        if not isinstance(scenario, dict):
            errors.append(f"{label} must be an object")
            continue
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            errors.append(f"{label}.scenario_id is required")
            continue
        if scenario_id in seen_ids:
            errors.append(f"duplicate scenario_id {scenario_id}")
        seen_ids.add(scenario_id)
        category = scenario.get("category")
        if not isinstance(category, str) or not category:
            errors.append(f"{scenario_id}.category is required")
        else:
            seen_categories.add(category)

        try:
            job = ParsedJobSchema.model_validate(scenario.get("job"))
        except Exception as exc:  # noqa: BLE001 - sample validity boundary
            errors.append(f"{scenario_id}: invalid job schema: {type(exc).__name__}")
            continue
        resume_payload = scenario.get("resume")
        resume: ParsedResumeSchema | None = None
        if resume_payload is not None:
            try:
                resume = ParsedResumeSchema.model_validate(resume_payload)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"{scenario_id}: invalid resume schema: {type(exc).__name__}"
                )
                continue
        try:
            match_result = MatchResultSchema.model_validate(
                scenario.get("match_result")
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"{scenario_id}: invalid match_result schema: "
                f"{type(exc).__name__}"
            )
            continue

        ground_truth = scenario.get("ground_truth")
        if not isinstance(ground_truth, dict):
            errors.append(f"{scenario_id}: ground_truth is required")
            continue
        score_range = ground_truth.get("expected_score_range")
        if (
            not isinstance(score_range, list)
            or len(score_range) != 2
            or not all(isinstance(value, (int, float)) for value in score_range)
            or score_range[0] > score_range[1]
        ):
            errors.append(f"{scenario_id}: invalid expected_score_range")
        elif not (score_range[0] <= match_result.overall_score <= score_range[1]):
            errors.append(
                f"{scenario_id}: match_result.overall_score is outside the "
                "declared expected_score_range"
            )

        skills_ground_truth = ground_truth.get("skills_ground_truth")
        if not isinstance(skills_ground_truth, dict):
            errors.append(f"{scenario_id}: skills_ground_truth is required")
            continue
        job_skills = [*job.required_skills, *job.preferred_skills]
        if set(skills_ground_truth) != set(job_skills):
            errors.append(
                f"{scenario_id}: ground-truth skills must exactly match job "
                "required + preferred skills"
            )
        for skill, truth in skills_ground_truth.items():
            if not isinstance(truth, dict):
                errors.append(f"{scenario_id}/{skill}: truth must be an object")
                continue
            status = truth.get("expected_status")
            if status not in CANONICAL_STATUSES:
                errors.append(
                    f"{scenario_id}/{skill}: unsupported expected_status "
                    f"{status!r}"
                )
            spans = truth.get("expected_evidence_spans")
            if not isinstance(spans, list):
                errors.append(
                    f"{scenario_id}/{skill}: expected_evidence_spans must be "
                    "a list"
                )
                continue
            if resume is None and spans:
                errors.append(
                    f"{scenario_id}/{skill}: evidence spans cannot be expected "
                    "without a parsed resume"
                )
                continue
            for span in spans:
                if not isinstance(span, dict):
                    errors.append(f"{scenario_id}/{skill}: invalid span")
                    continue
                section = span.get("section")
                quote = span.get("quote")
                verified = verifier.find(
                    resume,
                    section=section,
                    quote=quote,
                    field_name=span.get("field_name"),
                    item_index=span.get("item_index"),
                )
                if verified is None:
                    errors.append(
                        f"{scenario_id}/{skill}: expected quote is not present "
                        f"in section {section!r}"
                    )

        expected_inquiries = ground_truth.get("expected_inquiries")
        if not isinstance(expected_inquiries, list) or not all(
            isinstance(value, str) for value in expected_inquiries
        ):
            errors.append(f"{scenario_id}: expected_inquiries must be strings")

    categories = metadata.get("categories") if isinstance(metadata, dict) else []
    if isinstance(categories, list):
        expected_categories = set(categories)
        if seen_categories != expected_categories:
            errors.append(
                "scenario categories do not match metadata.categories"
            )
    return errors


def _precision(tp: int, fp: int, fn: int) -> float:
    if tp + fp == 0:
        return 1.0 if fn == 0 else 0.0
    return tp / (tp + fp)


def _recall(tp: int, fn: int) -> float:
    if tp + fn == 0:
        return 1.0
    return tp / (tp + fn)


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _normalize_inquiry(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _span_matches(
    excerpt: EvidenceExcerpt,
    expected: dict,
) -> bool:
    section = expected.get("section")
    quote = expected.get("quote")
    field_name = expected.get("field_name")
    item_index = expected.get("item_index")
    if not isinstance(section, str) or not isinstance(quote, str):
        return False
    if excerpt.section != section:
        return False
    if field_name is not None and excerpt.field_name != field_name:
        return False
    if item_index is not None and excerpt.item_index != item_index:
        return False
    return excerpt.quote.strip().casefold() == quote.strip().casefold()


async def evaluate_dataset(
    dataset: dict,
    *,
    dataset_path: str | Path | None = None,
) -> EvaluationReport:
    """Run the full benchmark using only in-memory, deterministic fakes."""
    if dataset_path is not None:
        dataset = load_golden_dataset(dataset_path)

    errors = _validate_dataset(dataset)
    scenarios = dataset.get("scenarios") if isinstance(dataset, dict) else []
    verifier = EvidenceVerifier()

    confusion = {status: _Confusion() for status in CANONICAL_STATUSES}
    present_classes: set[str] = set()
    total_skills = 0

    total_excerpts = 0
    invalid_excerpts = 0
    expected_span_count = 0
    matched_span_count = 0

    retrieved_inquiry_count = 0
    matched_retrieved_inquiry_count = 0
    expected_inquiry_count = 0
    matched_expected_inquiry_count = 0

    raw_contradiction_count = 0
    post_fallback_contradiction_count = 0
    evaluated_scenarios = 0

    for scenario in scenarios or []:
        scenario_id = scenario.get("scenario_id", "unknown")
        try:
            job = ParsedJobSchema.model_validate(scenario["job"])
            resume_payload = scenario.get("resume")
            resume = (
                ParsedResumeSchema.model_validate(resume_payload)
                if resume_payload is not None
                else None
            )
            match_result = MatchResultSchema.model_validate(
                scenario["match_result"]
            )
            truth = scenario["ground_truth"]
            narrative = scenario.get("narrative") or {}
            narrative_service = _ScenarioNarrative(
                summary=str(narrative.get("summary") or ""),
                match_score=float(
                    narrative.get("match_score", match_result.overall_score)
                ),
            )
            service = MatchExplanationService(
                narrative_service=narrative_service
            )
            response = await service.build_explanation(
                application_id=uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"explainability-golden:{scenario_id}",
                ),
                match_result=match_result,
                parsed_resume=resume,
                parsed_job=job,
            )
        except Exception as exc:  # noqa: BLE001 - sample-validity boundary
            errors.append(
                f"{scenario_id}: explanation evaluation failed: "
                f"{type(exc).__name__}"
            )
            continue

        evaluated_scenarios += 1

        if not (
            truth["expected_score_range"][0]
            <= response.overall_score
            <= truth["expected_score_range"][1]
        ):
            errors.append(
                f"{scenario_id}: response score is outside expected range"
            )

        by_skill = {
            evaluation.skill_name.casefold(): evaluation
            for evaluation in response.skill_evaluations
        }
        for skill, skill_truth in truth["skills_ground_truth"].items():
            expected = skill_truth["expected_status"]
            prediction = by_skill.get(skill.casefold())
            predicted = prediction.status if prediction is not None else "__missing__"
            present_classes.add(expected)
            total_skills += 1
            for status in CANONICAL_STATUSES:
                if expected == status and predicted == status:
                    confusion[status].tp += 1
                elif expected != status and predicted == status:
                    confusion[status].fp += 1
                elif expected == status and predicted != status:
                    confusion[status].fn += 1
            if prediction is None:
                errors.append(
                    f"{scenario_id}: skill {skill!r} was not evaluated"
                )

            for expected_span in skill_truth["expected_evidence_spans"]:
                expected_span_count += 1
                if any(
                    _span_matches(excerpt, expected_span)
                    for excerpt in response.evidence
                ):
                    matched_span_count += 1
                else:
                    errors.append(
                        f"{scenario_id}/{skill}: expected evidence span was "
                        "not retrieved"
                    )

        for excerpt in response.evidence:
            total_excerpts += 1
            if verifier.verify(resume, excerpt) is None:
                invalid_excerpts += 1
                errors.append(
                    f"{scenario_id}: evidence quote is not a verbatim "
                    f"substring of section {excerpt.section!r}"
                )

        expected_roles = truth["experience_ground_truth"][
            "expected_role_evaluations_count"
        ]
        if len(response.experience_evaluations) != expected_roles:
            errors.append(
                f"{scenario_id}: expected {expected_roles} role evaluations, "
                f"got {len(response.experience_evaluations)}"
            )

        expected_inquiries = {
            _normalize_inquiry(value)
            for value in truth["expected_inquiries"]
        }
        retrieved_inquiries = {
            _normalize_inquiry(value) for value in response.areas_for_inquiry
        }
        retrieved_inquiry_count += len(retrieved_inquiries)
        matched_retrieved_inquiry_count += len(
            retrieved_inquiries & expected_inquiries
        )
        expected_inquiry_count += len(expected_inquiries)
        matched_expected_inquiry_count += len(
            expected_inquiries & retrieved_inquiries
        )
        if any(
            "lacks" in inquiry.casefold() for inquiry in response.areas_for_inquiry
        ):
            errors.append(
                f"{scenario_id}: inquiry text falsely asserts missing skills"
            )

        raw_response = SimpleNamespace(
            match_score=narrative_service.match_score,
            summary=narrative_service.summary,
        )
        raw_contradiction = _narrative_contradicts_score(
            raw_response,
            narrative_service.summary,
            match_result.overall_score,
        )
        if raw_contradiction:
            raw_contradiction_count += 1
            if response.summary_source != "deterministic":
                errors.append(
                    f"{scenario_id}: raw contradiction was not replaced by "
                    "the deterministic fallback"
                )
        if _narrative_contradicts_score(
            SimpleNamespace(match_score=response.overall_score),
            response.summary,
            response.overall_score,
        ):
            post_fallback_contradiction_count += 1
            errors.append(
                f"{scenario_id}: final user-visible summary contradicts the "
                "authoritative score"
            )

    class_metrics: dict[str, ClassMetrics] = {}
    for status, counts in confusion.items():
        precision = _precision(counts.tp, counts.fp, counts.fn)
        recall = _recall(counts.tp, counts.fn)
        class_metrics[status] = ClassMetrics(
            true_positives=counts.tp,
            false_positives=counts.fp,
            false_negatives=counts.fn,
            precision=precision,
            recall=recall,
            f1=_f1(precision, recall),
        )

    micro_f1 = (
        sum(counts.tp for counts in confusion.values()) / total_skills
        if total_skills
        else 0.0
    )
    macro_f1 = (
        sum(class_metrics[status].f1 for status in present_classes)
        / len(present_classes)
        if present_classes
        else 0.0
    )
    quote_integrity_precision = (
        (total_excerpts - invalid_excerpts) / total_excerpts
        if total_excerpts
        else 1.0
    )
    evidence_recall = (
        matched_span_count / expected_span_count
        if expected_span_count
        else 1.0
    )
    inquiry_precision = (
        matched_retrieved_inquiry_count / retrieved_inquiry_count
        if retrieved_inquiry_count
        else 1.0
    )
    inquiry_recall = (
        matched_expected_inquiry_count / expected_inquiry_count
        if expected_inquiry_count
        else 1.0
    )
    raw_rate = (
        raw_contradiction_count / evaluated_scenarios
        if evaluated_scenarios
        else 0.0
    )
    post_rate = (
        post_fallback_contradiction_count / evaluated_scenarios
        if evaluated_scenarios
        else 0.0
    )

    return EvaluationReport(
        scenario_count=evaluated_scenarios,
        skill_count=total_skills,
        class_metrics=class_metrics,
        micro_f1=micro_f1,
        macro_f1=macro_f1,
        quote_integrity_precision=quote_integrity_precision,
        total_excerpts=total_excerpts,
        evidence_recall=evidence_recall,
        expected_span_count=expected_span_count,
        matched_span_count=matched_span_count,
        inquiry_precision=inquiry_precision,
        inquiry_recall=inquiry_recall,
        retrieved_inquiry_count=retrieved_inquiry_count,
        expected_inquiry_count=expected_inquiry_count,
        raw_contradiction_rate=raw_rate,
        raw_contradiction_count=raw_contradiction_count,
        post_fallback_contradiction_rate=post_rate,
        post_fallback_contradiction_count=post_fallback_contradiction_count,
        errors=errors,
    )
