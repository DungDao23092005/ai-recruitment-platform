"""Deterministic, evidence-grounded explanation of an application match.

Feature 5 (Phase 1). This service composes the **existing** deterministic
matching result (``MatchResultSchema``) with the candidate's parsed resume to
produce an explanation that a recruiter can trust. It never recalculates,
rounds or alters any score produced by ``MatchingEngine``.

Every candidate claim is grounded through the deterministic
``EvidenceVerifier``. When no verifiable evidence exists, the claim is
downgraded to ``not_evidenced_in_cv`` / ``insufficient_data`` and the missing
source is recorded in ``data_limitations`` - never fabricated.

The service optionally reuses the existing ``ExplainableAIService`` to produce
the free-form summary. This is best-effort: if the provider fails, the service
degrades to a deterministic summary and records the limitation. AI-generated
narrative (``summary_source == "ai_generated"``) is **not** quote-verified; only
the evidence excerpts and skill/experience evaluations pass through the
deterministic verifier. ``model_version`` records the provider's real configured
model name when available and stays ``None`` otherwise.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.ai.matching.evidence_verifier import EvidenceVerifier
from app.core.exceptions import (
    AIError,
    AIProviderQuotaExceededError,
    AIProviderUnavailableError,
    EmptyDocumentError,
    InvalidDocumentError,
    MatchExplanationRefreshError,
)
from app.core.telemetry.explainability_telemetry import (
    ExplainabilityTelemetryEvent,
    TelemetryErrorCode,
    TelemetryOutcome,
    build_explainability_event,
    emit_explainability_event,
    normalize_token_usage,
)
from app.schemas.ai_explanation import (
    ApplicationMatchExplanationResponse,
    EvidenceExcerpt,
    ExperienceEvaluation,
    ScoreBreakdown,
    SkillEvaluation,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema

_YEAR_RE = re.compile(r"(\d{4})")

# Deterministic narrative-consistency checks. These are intentionally narrow:
# they only recognise explicit match-score claims (``82/100``,
# ``82 out of 100``, ``score 82%``, ``95% match``), never arbitrary numbers or
# keywords. They are not semantic fact verification.
_SCORE_TOLERANCE = 0.5
_SCORE_CLAIM_PATTERNS = (
    re.compile(
        r"(?P<value>\d{1,3}(?:[.,]\d+)?)\s*(?:/\s*100|out\s+of\s+100)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:score|điểm)[^\d\n]{0,20}(?P<value>\d{1,3}(?:[.,]\d+)?)\s*%",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<value>\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:match|khớp)",
        re.IGNORECASE,
    ),
)


def _parse_claimed_score(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return None


def _summary_score_claims(summary: str) -> list[float]:
    claims: list[float] = []
    for pattern in _SCORE_CLAIM_PATTERNS:
        for match in pattern.finditer(summary):
            value = _parse_claimed_score(match.group("value"))
            if value is not None:
                claims.append(value)
    return claims


def _narrative_contradicts_score(
    response: object,
    summary: str,
    overall_score: object,
) -> bool:
    """Return ``True`` only for an explicit, reliable score contradiction.

    Checks the structured ``match_score`` field (when present) and explicit
    numeric score claims in the prose. A tolerance of 0.5 absorbs harmless
    display rounding while still rejecting a clearly different score.
    """
    try:
        authoritative = float(overall_score)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False

    claimed_match_score = getattr(response, "match_score", None)
    if (
        isinstance(claimed_match_score, (int, float))
        and not isinstance(claimed_match_score, bool)
        and abs(float(claimed_match_score) - authoritative) > _SCORE_TOLERANCE
    ):
        return True

    return any(
        abs(claimed - authoritative) > _SCORE_TOLERANCE
        for claimed in _summary_score_claims(summary)
    )


def _as_item_list(values: object) -> list:
    """Return a list from a possibly malformed collection value."""
    if isinstance(values, (list, tuple)):
        return list(values)
    return []


def _clean_skills(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def _derive_duration(
    start_date: str | None,
    end_date: str | None,
    is_current: bool,
) -> str | None:
    """Return a duration string only when reliably derivable, else ``None``."""
    start_match = _YEAR_RE.search(start_date) if isinstance(start_date, str) else None
    if start_match is None:
        return None
    start_year = start_match.group(1)
    if is_current:
        return f"{start_year} - present"
    end_match = _YEAR_RE.search(end_date) if isinstance(end_date, str) else None
    if end_match is None:
        return None
    return f"{start_year} - {end_match.group(1)}"


@dataclass(frozen=True)
class _NarrativeOutcome:
    summary: str
    model_version: str | None
    summary_source: str
    error_code: TelemetryErrorCode
    token_usage: dict[str, int | None] | None
    fallback_used: bool
    ai_attempted: bool
    telemetry_model_id: str | None = None
    refresh_error: MatchExplanationRefreshError | None = None


class MatchExplanationService:
    """Build an explainable, verifiable match explanation."""

    def __init__(
        self,
        narrative_service=None,
        verifier: EvidenceVerifier | None = None,
        *,
        telemetry_sink: Callable[[ExplainabilityTelemetryEvent], None]
        | None = None,
    ) -> None:
        self.narrative_service = narrative_service
        self.verifier = verifier or EvidenceVerifier()
        self.telemetry_sink = telemetry_sink

    # -- skill evaluation -------------------------------------------------

    def _find_related_skill_evidence(
        self,
        parsed_resume: ParsedResumeSchema,
        skill: str,
    ) -> EvidenceExcerpt | None:
        for index, exp in enumerate(
            _as_item_list(getattr(parsed_resume, "experiences", None))
        ):
            for used in _clean_skills(getattr(exp, "skills_used", None)):
                if used.lower() == skill.lower():
                    return self.verifier.find(
                        parsed_resume,
                        section="experiences",
                        quote=used,
                        field_name="skills_used",
                        item_index=index,
                    )
        for index, proj in enumerate(
            _as_item_list(getattr(parsed_resume, "projects", None))
        ):
            for used in _clean_skills(getattr(proj, "skills_used", None)):
                if used.lower() == skill.lower():
                    return self.verifier.find(
                        parsed_resume,
                        section="projects",
                        quote=used,
                        field_name="skills_used",
                        item_index=index,
                    )
        return None

    def _evaluate_skill(
        self,
        parsed_resume: ParsedResumeSchema | None,
        skill: str,
        requirement_type: str,
    ) -> SkillEvaluation:
        if parsed_resume is None:
            return SkillEvaluation(
                skill_name=skill,
                requirement_type=requirement_type,  # type: ignore[arg-type]
                status="insufficient_data",
                explanation=(
                    f"No parsed CV is available, so '{skill}' could not be "
                    "evaluated against the candidate's evidence."
                ),
                evidence=[],
            )

        resume_skills = {
            value.lower() for value in _clean_skills(parsed_resume.skills)
        }
        if skill.lower() in resume_skills:
            evidence = self.verifier.find(
                parsed_resume, section="skills", quote=skill
            )
            return SkillEvaluation(
                skill_name=skill,
                requirement_type=requirement_type,  # type: ignore[arg-type]
                status="matched_evidenced",
                explanation=(
                    f"'{skill}' is listed in the candidate's skills and was "
                    "verified against the parsed CV."
                ),
                evidence=[evidence] if evidence is not None else [],
            )

        related = self._find_related_skill_evidence(parsed_resume, skill)
        if related is not None:
            return SkillEvaluation(
                skill_name=skill,
                requirement_type=requirement_type,  # type: ignore[arg-type]
                status="partially_matched",
                explanation=(
                    f"'{skill}' is not listed as a discrete skill, but it "
                    "appears in the candidate's described experience/projects."
                ),
                evidence=[related],
            )

        return SkillEvaluation(
            skill_name=skill,
            requirement_type=requirement_type,  # type: ignore[arg-type]
            status="not_evidenced_in_cv",
            explanation=(
                f"'{skill}' was not found in the provided CV. This is not a "
                "claim that the candidate lacks the skill - it should be "
                "verified in an interview."
            ),
            evidence=[],
        )

    # -- experience evaluation -------------------------------------------

    def _evaluate_experiences(
        self,
        parsed_resume: ParsedResumeSchema | None,
        parsed_job: ParsedJobSchema | None,
    ) -> list[ExperienceEvaluation]:
        if parsed_resume is None:
            return []
        experiences = _as_item_list(getattr(parsed_resume, "experiences", None))
        required_lower = {
            value.lower()
            for value in _clean_skills(
                parsed_job.required_skills if parsed_job else None
            )
        }
        evaluations: list[ExperienceEvaluation] = []
        for index, exp in enumerate(experiences):
            used = _clean_skills(getattr(exp, "skills_used", None))
            overlap = [skill for skill in used if skill.lower() in required_lower]
            if overlap:
                relevance = "relevant_skills"
                explanation = (
                    "Role used required skills: " + ", ".join(overlap) + "."
                )
                evidence = [
                    excerpt
                    for excerpt in [
                        self.verifier.find(
                            parsed_resume,
                            section="experiences",
                            quote=overlap[0],
                            field_name="skills_used",
                            item_index=index,
                        )
                    ]
                    if excerpt is not None
                ]
            elif required_lower:
                relevance = "no_required_skill_overlap"
                explanation = (
                    "No required skill from the job description is evidenced "
                    "in this role."
                )
                evidence = []
            else:
                relevance = "no_requirement_to_compare"
                explanation = (
                    "The job description lists no required skills to compare "
                    "against."
                )
                evidence = []

            evaluations.append(
                ExperienceEvaluation(
                    role_title=getattr(exp, "position", None) or None,
                    company=getattr(exp, "company", None) or None,
                    duration=_derive_duration(
                        getattr(exp, "start_date", None),
                        getattr(exp, "end_date", None),
                        bool(getattr(exp, "is_current", False)),
                    ),
                    relevance=relevance,
                    explanation=explanation,
                    evidence=evidence,
                )
            )
        return evaluations

    # -- narrative --------------------------------------------------------

    async def _build_summary(
        self,
        match_result: MatchResultSchema,
        parsed_resume: ParsedResumeSchema | None,
        parsed_job: ParsedJobSchema | None,
        data_limitations: list[str],
        narrative_service=None,
        *,
        raise_on_failure: bool = False,
    ) -> _NarrativeOutcome:
        """Build the narrative outcome plus bounded telemetry metadata.

        ``raise_on_failure`` does not raise directly: it records the typed
        refresh error on the outcome so the caller can emit telemetry before
        re-raising. This keeps the public refresh semantics unchanged while
        ensuring provider failures are observable.
        """
        fallback_summary = (
            f"Deterministic match score {match_result.overall_score:.2f}/100 "
            "(scores are produced by the matching engine and copied verbatim)."
        )
        configured_model: str | None = None
        ai_attempted = narrative_service is not None
        if narrative_service is not None:
            provider = getattr(narrative_service, "llm_provider", None)
            raw_model = getattr(provider, "model_name", None)
            configured_model = (
                raw_model.strip()
                if isinstance(raw_model, str) and raw_model.strip()
                else None
            )

        def fallback(
            error_code: TelemetryErrorCode,
            *,
            token_usage: dict[str, int | None] | None = None,
            refresh_error: MatchExplanationRefreshError | None = None,
        ) -> _NarrativeOutcome:
            return _NarrativeOutcome(
                summary=fallback_summary,
                model_version=None,
                summary_source="deterministic",
                error_code=error_code,
                token_usage=token_usage,
                fallback_used=ai_attempted,
                ai_attempted=ai_attempted,
                telemetry_model_id=configured_model,
                refresh_error=refresh_error,
            )

        if narrative_service is not None:
            try:
                response = await narrative_service.explain_match(
                    match_result=match_result,
                    candidate=parsed_resume,
                    job=parsed_job,
                )
                token_usage = normalize_token_usage(
                    getattr(response, "_token_usage", None)
                )
                raw_summary = getattr(response, "summary", None)
                summary = (
                    raw_summary.strip()
                    if isinstance(raw_summary, str)
                    else ""
                )
                if not summary:
                    refresh_error = (
                        MatchExplanationRefreshError("empty_narrative")
                        if raise_on_failure
                        else None
                    )
                    if not raise_on_failure:
                        data_limitations.append(
                            "The AI narrative was empty or malformed; a "
                            "deterministic summary was used instead."
                        )
                    return fallback(
                        TelemetryErrorCode.INVALID_NARRATIVE,
                        token_usage=token_usage,
                        refresh_error=refresh_error,
                    )
                if _narrative_contradicts_score(
                    response, summary, getattr(match_result, "overall_score", None)
                ):
                    refresh_error = (
                        MatchExplanationRefreshError("score_contradiction")
                        if raise_on_failure
                        else None
                    )
                    if not raise_on_failure:
                        data_limitations.append(
                            "The AI narrative was rejected because it contained "
                            "a match-score claim that conflicts with the "
                            "deterministic score; a deterministic summary was "
                            "used instead."
                        )
                    return fallback(
                        TelemetryErrorCode.SCORE_CONTRADICTION,
                        token_usage=token_usage,
                        refresh_error=refresh_error,
                    )

                data_limitations.append(
                    "The summary is AI-generated narrative and is not "
                    "quote-verified. Only the evidence excerpts and "
                    "evaluations are deterministically verified against "
                    "the parsed CV."
                )
                return _NarrativeOutcome(
                    summary=summary,
                    model_version=configured_model,
                    summary_source="ai_generated",
                    error_code=TelemetryErrorCode.NONE,
                    token_usage=token_usage,
                    fallback_used=False,
                    ai_attempted=True,
                    telemetry_model_id=configured_model,
                )
            except AIProviderQuotaExceededError as exc:
                refresh_error = (
                    MatchExplanationRefreshError(
                        "provider_quota_exceeded",
                        http_status=429,
                        retry_after=getattr(exc, "retry_after", None),
                    )
                    if raise_on_failure
                    else None
                )
                if not raise_on_failure:
                    data_limitations.append(
                        "The AI narrative explanation was unavailable; a "
                        "deterministic summary was used instead."
                    )
                return fallback(
                    TelemetryErrorCode.PROVIDER_QUOTA_EXCEEDED,
                    refresh_error=refresh_error,
                )
            except AIProviderUnavailableError as exc:
                refresh_error = (
                    MatchExplanationRefreshError(
                        "provider_unavailable",
                        http_status=503,
                        retry_after=getattr(exc, "retry_after", None),
                    )
                    if raise_on_failure
                    else None
                )
                if not raise_on_failure:
                    data_limitations.append(
                        "The AI narrative explanation was unavailable; a "
                        "deterministic summary was used instead."
                    )
                return fallback(
                    TelemetryErrorCode.PROVIDER_UNAVAILABLE,
                    refresh_error=refresh_error,
                )
            except AIError as exc:
                error_code = (
                    TelemetryErrorCode.INVALID_NARRATIVE
                    if isinstance(exc, (EmptyDocumentError, InvalidDocumentError))
                    else TelemetryErrorCode.PROVIDER_ERROR
                )
                refresh_error = (
                    MatchExplanationRefreshError(
                        "invalid_narrative"
                        if error_code is TelemetryErrorCode.INVALID_NARRATIVE
                        else "provider_error"
                    )
                    if raise_on_failure
                    else None
                )
                if not raise_on_failure:
                    data_limitations.append(
                        "The AI narrative explanation was unavailable; a "
                        "deterministic summary was used instead."
                    )
                return fallback(
                    error_code, refresh_error=refresh_error
                )
            except TimeoutError:
                refresh_error = (
                    MatchExplanationRefreshError("provider_error")
                    if raise_on_failure
                    else None
                )
                if not raise_on_failure:
                    data_limitations.append(
                        "The AI narrative explanation failed unexpectedly; a "
                        "deterministic summary was used instead."
                    )
                return fallback(
                    TelemetryErrorCode.PROVIDER_TIMEOUT,
                    refresh_error=refresh_error,
                )
            except Exception:  # noqa: BLE001 - never fail the explanation
                refresh_error = (
                    MatchExplanationRefreshError("provider_error")
                    if raise_on_failure
                    else None
                )
                if not raise_on_failure:
                    data_limitations.append(
                        "The AI narrative explanation failed unexpectedly; a "
                        "deterministic summary was used instead."
                    )
                return fallback(
                    TelemetryErrorCode.PROVIDER_ERROR,
                    refresh_error=refresh_error,
                )

        return fallback(TelemetryErrorCode.NONE)

    # -- public API -------------------------------------------------------

    async def build_explanation(
        self,
        application_id: uuid.UUID,
        match_result: MatchResultSchema,
        parsed_resume: ParsedResumeSchema | None,
        parsed_job: ParsedJobSchema | None,
    ) -> ApplicationMatchExplanationResponse:
        """Build an explanation using the configured narrative service."""
        return await self._build_explanation(
            application_id=application_id,
            match_result=match_result,
            parsed_resume=parsed_resume,
            parsed_job=parsed_job,
            narrative_service=self.narrative_service,
        )

    async def build_deterministic_explanation(
        self,
        application_id: uuid.UUID,
        match_result: MatchResultSchema,
        parsed_resume: ParsedResumeSchema | None,
        parsed_job: ParsedJobSchema | None,
    ) -> ApplicationMatchExplanationResponse:
        """Build an explanation without any external AI/narrative provider.

        The regular GET endpoint uses this explicit path so a cache miss can
        never trigger a provider call, even if the service was constructed
        with a narrative service.
        """
        return await self._build_explanation(
            application_id=application_id,
            match_result=match_result,
            parsed_resume=parsed_resume,
            parsed_job=parsed_job,
            narrative_service=None,
        )

    async def build_refresh_explanation(
        self,
        application_id: uuid.UUID,
        match_result: MatchResultSchema,
        parsed_resume: ParsedResumeSchema | None,
        parsed_job: ParsedJobSchema | None,
    ) -> ApplicationMatchExplanationResponse:
        """Build via the configured narrative and require real AI output.

        Unlike ``build_explanation`` (best-effort with a deterministic
        fallback), this raises a typed error when no narrative service is
        configured, the provider fails, returns an empty/malformed narrative,
        or produces a score-contradicting narrative. The quota-controlled
        refresh path uses this so a fallback is never mistaken for a
        successful paid AI refresh.
        """
        if self.narrative_service is None:
            raise MatchExplanationRefreshError(
                "narrative_service_unavailable"
            )
        return await self._build_explanation(
            application_id=application_id,
            match_result=match_result,
            parsed_resume=parsed_resume,
            parsed_job=parsed_job,
            narrative_service=self.narrative_service,
            raise_narrative_failure=True,
        )

    async def _build_explanation(
        self,
        application_id: uuid.UUID,
        match_result: MatchResultSchema,
        parsed_resume: ParsedResumeSchema | None,
        parsed_job: ParsedJobSchema | None,
        narrative_service=None,
        *,
        raise_narrative_failure: bool = False,
    ) -> ApplicationMatchExplanationResponse:
        started_at = time.perf_counter()
        required_skills = _clean_skills(
            parsed_job.required_skills if parsed_job else None
        )
        preferred_skills = _clean_skills(
            parsed_job.preferred_skills if parsed_job else None
        )

        skill_evaluations: list[SkillEvaluation] = [
            self._evaluate_skill(parsed_resume, skill, "required")
            for skill in required_skills
        ]
        skill_evaluations.extend(
            self._evaluate_skill(parsed_resume, skill, "preferred")
            for skill in preferred_skills
        )

        experience_evaluations = self._evaluate_experiences(
            parsed_resume, parsed_job
        )

        data_limitations: list[str] = []
        if parsed_resume is None:
            data_limitations.append(
                "No parsed CV data is available for this application; skill "
                "and experience evaluations are limited to the job requirements."
            )
        else:
            if not _as_item_list(getattr(parsed_resume, "experiences", None)):
                data_limitations.append(
                    "The CV contains no structured work experience entries."
                )
            if (
                parsed_job is not None
                and (parsed_job.minimum_years_experience or 0) > 0
                and getattr(parsed_resume, "total_years_experience", None) is None
            ):
                data_limitations.append(
                    "Total years of experience could not be derived from the CV."
                )

        key_strengths: list[str] = []
        if parsed_resume is not None and getattr(parsed_resume, "skills", None):
            matching = sorted(
                {skill for skill in match_result.matching_skills if skill}
            )
            if matching:
                key_strengths.append(
                    "Candidate skills matching the job: "
                    + ", ".join(matching)
                    + "."
                )
        for evaluation in experience_evaluations:
            if evaluation.relevance == "relevant_skills":
                label = evaluation.role_title or evaluation.company or "a role"
                key_strengths.append(
                    f"Relevant experience as {label}."
                )

        areas_for_inquiry: list[str] = [
            f"Probe depth of experience with '{skill}' - not found in the "
            "provided CV."
            for skill in match_result.skill_gap
            if skill
        ]
        if (
            parsed_job is not None
            and (parsed_job.minimum_years_experience or 0) > 0
            and (
                parsed_resume is None
                or getattr(parsed_resume, "total_years_experience", None) is None
            )
        ):
            areas_for_inquiry.append(
                "Confirm the candidate's total years of experience in an "
                "interview."
            )

        evidence: list[EvidenceExcerpt] = []
        seen: set[tuple] = set()
        for evaluation in [*skill_evaluations, *experience_evaluations]:
            for excerpt in evaluation.evidence:
                key = (
                    excerpt.section,
                    excerpt.field_name,
                    excerpt.item_index,
                    excerpt.quote,
                )
                if key not in seen:
                    seen.add(key)
                    evidence.append(excerpt)

        narrative = await self._build_summary(
            match_result,
            parsed_resume,
            parsed_job,
            data_limitations,
            narrative_service,
            raise_on_failure=raise_narrative_failure,
        )

        if narrative.refresh_error is not None:
            telemetry_outcome = TelemetryOutcome.ERROR
        elif narrative.fallback_used:
            telemetry_outcome = TelemetryOutcome.FALLBACK
        else:
            telemetry_outcome = TelemetryOutcome.SUCCESS
        emit_explainability_event(
            build_explainability_event(
                application_id=application_id,
                outcome=telemetry_outcome,
                fallback_used=narrative.fallback_used,
                error_code=narrative.error_code,
                model_id=narrative.telemetry_model_id,
                token_usage=narrative.token_usage,
                latency_ms=int(
                    (time.perf_counter() - started_at) * 1000
                ),
                cache_state="not_cached",
                summary_source=narrative.summary_source,
                ai_attempted=narrative.ai_attempted,
            ),
            sink=self.telemetry_sink,
        )

        if narrative.refresh_error is not None:
            raise narrative.refresh_error

        return ApplicationMatchExplanationResponse(
            application_id=application_id,
            overall_score=match_result.overall_score,
            score_breakdown=ScoreBreakdown(
                overall_score=match_result.overall_score,
                cosine_similarity=match_result.cosine_similarity,
                skill_coverage_score=match_result.skill_coverage_score,
                preferred_skill_coverage_score=(
                    match_result.preferred_skill_coverage_score
                ),
                experience_match_score=match_result.experience_match_score,
                education_score=match_result.education_score,
                project_score=match_result.project_score,
            ),
            summary=narrative.summary,
            summary_source=narrative.summary_source,
            skill_evaluations=skill_evaluations,
            experience_evaluations=experience_evaluations,
            key_strengths=key_strengths,
            areas_for_inquiry=areas_for_inquiry,
            evidence=evidence,
            data_limitations=data_limitations,
            confidence=None,
            model_version=narrative.model_version,
            generated_at=datetime.now(timezone.utc),
            cache_state="not_cached",
        )
