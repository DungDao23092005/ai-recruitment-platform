from __future__ import annotations

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.ai.providers.gemini_provider import GeminiLLMProvider
from app.core.exceptions import AIError, EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_explanation import ExplainMatchRequest, ExplainMatchResponse
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema

_SYSTEM_INSTRUCTION = (
    "Bn lA tr lA tuyn dng AI gii thA-ch kt qu `i sAnh gi_a cng viAn "
    "vA tin tuyn dng. Ch% s- dng d_ kin c cung cp. KhA'ng t suy oAn, "
    "khA'ng b<a 	 k1 nng, kinh nghim hoc thA'ng tin khA'ng cA3 trong d_ kin. "
    "Nu thA'ng tin khA'ng c cung cp, hAy nA3i rA thA'ng tin A3 khA'ng c "
    "cung cp thay vA oAn. Tuyt `i khA'ng tA-nh li hoc thay  i im s.\n"
    "Cung cp cAc bng ch>ng (evidence) rA rAng t H s cng viAn (candidate_cv) "
    "hoc MA' t cA'ng vic (job_description)."
)


class ExplainableAIService:
    """Explain an existing match result using an LLM without recalculating scores.

    `MatchResultSchema` is the source of truth: this service only builds a
    grounded prompt from the provided facts and asks the LLM to explain them.
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider | None = None,
    ) -> None:
        self.llm_provider = llm_provider or GeminiLLMProvider()

    @staticmethod
    def _format_optional_list(label: str, values: list[str]) -> str:
        if not values:
            return f"{label}: (khA'ng cA3 thA'ng tin)\n"
        return f"{label}: {', '.join(values)}\n"

    def build_prompt(
        self,
        match_result: MatchResultSchema,
        candidate: ParsedResumeSchema | None = None,
        job: ParsedJobSchema | None = None,
    ) -> str:
        """Build a grounded prompt embedding only the provided facts."""
        lines: list[str] = [
            "D>i Ay lA kt qu `i sAnh vA thA'ng tin A cung cp.",
            "",
            "--- MATCH RESULT ---",
            f"overall_score: {match_result.overall_score}",
            f"semantic_score: {match_result.cosine_similarity}",
            f"skill_score: {match_result.skill_coverage_score}",
            f"experience_score: {match_result.experience_match_score}",
            f"education_score: {getattr(match_result, 'education_score', 0.0)}",
            f"project_score: {getattr(match_result, 'project_score', 0.0)}",
            self._format_optional_list(
                "matching_skills", match_result.matching_skills
            ).rstrip(),
            self._format_optional_list("skill_gap", match_result.skill_gap).rstrip(),
        ]
        if match_result.match_reasons:
            lines.append(
                "match_reasons: " + "; ".join(match_result.match_reasons)
            )
        else:
            lines.append("match_reasons: (khA'ng cA3 thA'ng tin)")

        lines.append("")
        lines.append("--- CANDIDATE ---")
        if candidate is None:
            lines.append("(thA'ng tin cng viAn khA'ng c cung cp)")
        else:
            lines.append(
                "full_name: " + (candidate.full_name or "(khA'ng cung cp)")
            )
            lines.append(
                "title: " + (candidate.title or "(khA'ng cung cp)")
            )
            lines.append(
                "total_years_experience: "
                + (
                    str(candidate.total_years_experience)
                    if candidate.total_years_experience is not None
                    else "(khA'ng cung cp)"
                )
            )
            lines.append(
                "summary: " + (candidate.summary or "(khA'ng cung cp)")
            )
            lines.append(
                self._format_optional_list("skills", candidate.skills).rstrip()
            )
            if hasattr(candidate, 'experiences') and candidate.experiences:
                lines.append("work_experience:")
                for exp in candidate.experiences:
                    lines.append(f" - {exp.position} at {exp.company} ({exp.start_date} - {exp.end_date}): {exp.description}")
            if hasattr(candidate, 'projects') and candidate.projects:
                lines.append("projects:")
                for proj in candidate.projects:
                    lines.append(f" - {proj.name}: {proj.description}")

        lines.append("")
        lines.append("--- JOB ---")
        if job is None:
            lines.append("(thA'ng tin tin tuyn dng khA'ng c cung cp)")
        else:
            lines.append("title: " + (job.title or "(khA'ng cung cp)"))
            lines.append(
                "summary: " + (job.summary or "(khA'ng cung cp)")
            )
            lines.append(
                "minimum_years_experience: "
                + (
                    str(job.minimum_years_experience)
                    if job.minimum_years_experience is not None
                    else "(khA'ng cung cp)"
                )
            )
            lines.append(
                self._format_optional_list(
                    "required_skills", job.required_skills
                ).rstrip()
            )
            lines.append(
                self._format_optional_list(
                    "preferred_skills", job.preferred_skills
                ).rstrip()
            )
            if hasattr(job, 'responsibilities') and job.responsibilities:
                lines.append(
                    self._format_optional_list(
                        "responsibilities", job.responsibilities
                    ).rstrip()
                )

        lines.append("")
        lines.append(
            "HAy to gii thA-ch theo schema ExplainMatchResponse. "
            "Ch% s- dng d_ kin c cung cp Y trAn."
        )
        return "\n".join(lines)

    async def explain_match(
        self,
        match_result: MatchResultSchema,
        candidate: ParsedResumeSchema | None = None,
        job: ParsedJobSchema | None = None,
    ) -> ExplainMatchResponse:
        """Explain a match result with grounded LLM output."""
        if match_result is None:
            raise InvalidDocumentError("match_result is required")

        request = ExplainMatchRequest(
            match_result=match_result,
            candidate=candidate,
            job=job,
        )

        if request.match_result.overall_score is None:
            raise EmptyDocumentError(
                "match_result has no overall_score to explain"
            )

        prompt = self.build_prompt(
            match_result=request.match_result,
            candidate=request.candidate,
            job=request.job,
        )

        try:
            response = await self.llm_provider.generate_structured_output(
                prompt=prompt,
                response_schema=ExplainMatchResponse,
                system_instruction=_SYSTEM_INSTRUCTION,
            )
        except AIError:
            raise
        except Exception as exc:
            raise InvalidDocumentError(
                f"AI explanation provider failed: {exc}"
            ) from exc

        return self._validate_response(response)

    @staticmethod
    def _validate_response(
        response: ExplainMatchResponse,
    ) -> ExplainMatchResponse:
        if response is None:
            raise InvalidDocumentError(
                "AI explanation returned no response"
            )
        if not response.summary or not response.summary.strip():
            raise InvalidDocumentError(
                "AI explanation returned an empty summary"
            )
        if not response.experience_analysis or not response.experience_analysis.strip():
            raise InvalidDocumentError(
                "AI explanation returned an empty experience_analysis"
            )
        if not response.recommendation or not response.recommendation.strip():
            raise InvalidDocumentError(
                "AI explanation returned an empty recommendation"
            )
        return response
