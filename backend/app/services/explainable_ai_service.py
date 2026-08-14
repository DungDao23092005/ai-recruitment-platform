from __future__ import annotations

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.ai.providers.gemini_provider import GeminiLLMProvider
from app.core.exceptions import AIError, EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_explanation import ExplainMatchRequest, ExplainMatchResponse
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema

_SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý tuyển dụng AI giải thích kết quả đối sánh giữa ứng viên "
    "và tin tuyển dụng. Chỉ sử dụng dữ kiện được cung cấp. Không tự suy đoán, "
    "không bịa đặt kỹ năng, kinh nghiệm hoặc thông tin không có trong dữ kiện. "
    "Nếu thông tin không được cung cấp, hãy nói rõ thông tin đó không được "
    "cung cấp thay vì đoán. Tuyệt đối không tính lại hoặc thay đổi điểm số."
)


class ExplainableAIService:
    """Explain an existing match result using an LLM without recalculating scores.

    ``MatchResultSchema`` is the source of truth: this service only builds a
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
            return f"{label}: (không có thông tin)\n"
        return f"{label}: {', '.join(values)}\n"

    def build_prompt(
        self,
        match_result: MatchResultSchema,
        candidate: ParsedResumeSchema | None = None,
        job: ParsedJobSchema | None = None,
    ) -> str:
        """Build a grounded prompt embedding only the provided facts."""
        lines: list[str] = [
            "Dưới đây là kết quả đối sánh và thông tin đã cung cấp.",
            "",
            "--- MATCH RESULT ---",
            f"overall_score: {match_result.overall_score}",
            f"cosine_similarity: {match_result.cosine_similarity}",
            f"skill_coverage_score: {match_result.skill_coverage_score}",
            f"experience_match_score: {match_result.experience_match_score}",
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
            lines.append("match_reasons: (không có thông tin)")

        lines.append("")
        lines.append("--- CANDIDATE ---")
        if candidate is None:
            lines.append("(thông tin ứng viên không được cung cấp)")
        else:
            lines.append(
                "full_name: " + (candidate.full_name or "(không cung cấp)")
            )
            lines.append(
                "title: " + (candidate.title or "(không cung cấp)")
            )
            lines.append(
                "total_years_experience: "
                + (
                    str(candidate.total_years_experience)
                    if candidate.total_years_experience is not None
                    else "(không cung cấp)"
                )
            )
            lines.append(
                "summary: " + (candidate.summary or "(không cung cấp)")
            )
            lines.append(
                self._format_optional_list("skills", candidate.skills).rstrip()
            )

        lines.append("")
        lines.append("--- JOB ---")
        if job is None:
            lines.append("(thông tin tin tuyển dụng không được cung cấp)")
        else:
            lines.append("title: " + (job.title or "(không cung cấp)"))
            lines.append(
                "summary: " + (job.summary or "(không cung cấp)")
            )
            lines.append(
                "minimum_years_experience: "
                + (
                    str(job.minimum_years_experience)
                    if job.minimum_years_experience is not None
                    else "(không cung cấp)"
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

        lines.append("")
        lines.append(
            "Hãy tạo giải thích theo schema ExplainMatchResponse. "
            "Chỉ sử dụng dữ kiện được cung cấp ở trên."
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
