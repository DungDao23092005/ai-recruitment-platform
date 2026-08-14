from __future__ import annotations

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.ai.providers.gemini_provider import GeminiLLMProvider
from app.core.exceptions import AIError, EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_interview import (
    GenerateInterviewQuestionsRequest,
    GenerateInterviewQuestionsResponse,
    InterviewQuestion,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema

_SYSTEM_INSTRUCTION = (
    "Bạn là Senior Talent Acquisition & Interview Architect chuyên thiết kế bộ "
    "câu hỏi phỏng vấn cho nhà tuyển dụng. Hãy tạo câu hỏi chuyên sâu, khách "
    "quan, phân loại rõ ràng Technical / Behavioral / Experience / Skill Gap. "
    "Chỉ sử dụng dữ kiện được cung cấp trong prompt. Không được bịa đặt kinh "
    "nghiệm của ứng viên, không bịa đặt kỹ năng, dự án, chứng chỉ hoặc quá "
    "trình làm việc. Nếu không có thông tin ứng viên, chỉ tạo câu hỏi dựa trên "
    "tin tuyển dụng. Trả lời bằng tiếng Việt chuyên nghiệp theo schema đã chỉ định."
)


class InterviewGeneratorService:
    """Generate interview questions grounded in job, candidate, and match facts.

    The service only embeds the facts provided by the caller into a prompt and
    requests a typed ``GenerateInterviewQuestionsResponse`` from the LLM. It
    never invents facts and validates the structured output before returning it.
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

    @staticmethod
    def _format_work_experiences(candidate: ParsedResumeSchema) -> str:
        if not candidate.experiences:
            return "work_experience: (không có thông tin)\n"
        lines: list[str] = ["work_experience:"]
        for exp in candidate.experiences:
            period = ""
            if exp.start_date or exp.end_date:
                period = (
                    f" ({exp.start_date or 'không rõ'} - "
                    f"{exp.end_date or 'Hiện tại'})"
                )
            lines.append(
                f"- {exp.position or 'không cung cấp'} @ "
                f"{exp.company or 'không cung cấp'}{period}"
            )
            if exp.description:
                lines.append(f"  description: {exp.description}")
            if exp.skills_used:
                lines.append(f"  skills: {', '.join(exp.skills_used)}")
        return "\n".join(lines) + "\n"

    def build_prompt(self, request: GenerateInterviewQuestionsRequest) -> str:
        """Build a grounded prompt embedding only the provided facts."""
        lines: list[str] = [
            "Dưới đây là dữ kiện đã cung cấp để tạo bộ câu hỏi phỏng vấn.",
            "",
            "--- JOB ---",
        ]
        job = request.job
        lines.append(f"title: {job.title or '(không cung cấp)'}")
        if job.summary:
            lines.append(f"summary: {job.summary}")
        lines.append(
            self._format_optional_list("required_skills", job.required_skills).rstrip()
        )
        lines.append(
            self._format_optional_list("preferred_skills", job.preferred_skills).rstrip()
        )
        lines.append(
            "minimum_years_experience: "
            + (
                str(job.minimum_years_experience)
                if job.minimum_years_experience is not None
                else "(không cung cấp)"
            )
        )

        lines.append("")
        lines.append("--- CANDIDATE ---")
        if request.candidate is None:
            lines.append("(thông tin ứng viên không được cung cấp)")
        else:
            candidate = request.candidate
            lines.append(f"title: {candidate.title or '(không cung cấp)'}")
            lines.append(
                "total_years_experience: "
                + (
                    str(candidate.total_years_experience)
                    if candidate.total_years_experience is not None
                    else "(không cung cấp)"
                )
            )
            lines.append(
                self._format_optional_list("skills", candidate.skills).rstrip()
            )
            lines.append(self._format_work_experiences(candidate).rstrip())

        lines.append("")
        lines.append("--- MATCH RESULT ---")
        if request.match_result is None:
            lines.append("(không có thông tin)")
        else:
            match_result = request.match_result
            lines.append(
                self._format_optional_list(
                    "matching_skills", match_result.matching_skills
                ).rstrip()
            )
            lines.append(
                self._format_optional_list(
                    "skill_gap", match_result.skill_gap
                ).rstrip()
            )

        lines.append("")
        lines.append("--- CONFIG ---")
        lines.append(f"num_questions: {request.num_questions}")
        lines.append(f"difficulty: {request.difficulty}")
        lines.append(
            self._format_optional_list(
                "focus_areas", request.focus_areas
            ).rstrip()
        )

        lines.append("")
        lines.append(
            "Hãy tạo bộ câu hỏi theo schema GenerateInterviewQuestionsResponse. "
            "Câu hỏi Skill Gap phải liên quan đến skill_gap thực tế trong MATCH "
            "RESULT nếu có. Câu hỏi Experience chỉ được dựa trên thông tin ứng "
            "viên thực sự có trong CANDIDATE."
        )
        return "\n".join(lines)

    async def generate_questions(
        self,
        request: GenerateInterviewQuestionsRequest,
    ) -> GenerateInterviewQuestionsResponse:
        """Generate a grounded set of interview questions."""
        self._require_job(request.job)

        prompt = self.build_prompt(request)

        try:
            response = await self.llm_provider.generate_structured_output(
                prompt=prompt,
                response_schema=GenerateInterviewQuestionsResponse,
                system_instruction=_SYSTEM_INSTRUCTION,
            )
        except AIError:
            raise
        except Exception as exc:
            raise InvalidDocumentError(
                f"AI interview generator provider failed: {exc}"
            ) from exc

        return self._validate_response(response, has_candidate=request.candidate is not None)

    @staticmethod
    def _require_job(job: ParsedJobSchema | None) -> None:
        if job is None:
            raise EmptyDocumentError("job is required")
        has_content = bool(
            job.title
            or job.summary
            or job.required_skills
            or job.preferred_skills
            or job.minimum_years_experience is not None
        )
        if not has_content:
            raise EmptyDocumentError("job has no content to generate questions from")

    @staticmethod
    def _validate_response(
        response: GenerateInterviewQuestionsResponse | None,
        has_candidate: bool,
    ) -> GenerateInterviewQuestionsResponse:
        if response is None:
            raise InvalidDocumentError(
                "AI interview generator returned no response"
            )
        if not response.job_title or not response.job_title.strip():
            raise InvalidDocumentError(
                "AI interview generator returned an empty job_title"
            )
        if not response.questions:
            raise InvalidDocumentError(
                "AI interview generator returned no questions"
            )

        validated: list[InterviewQuestion] = []
        for question in response.questions:
            if not question.question or not question.question.strip():
                raise InvalidDocumentError(
                    "AI interview generator returned an empty question"
                )
            if (
                not question.target_skill_or_topic
                or not question.target_skill_or_topic.strip()
            ):
                raise InvalidDocumentError(
                    "AI interview generator returned a question without "
                    "target_skill_or_topic"
                )
            if (
                not question.evaluation_criteria
                or not question.evaluation_criteria.strip()
            ):
                raise InvalidDocumentError(
                    "AI interview generator returned a question without "
                    "evaluation_criteria"
                )
            # Experience questions can only be grounded in candidate data.
            # Without a candidate, an "experience" question would be fabricated.
            if not has_candidate and question.category == "experience":
                continue
            validated.append(question)

        if not validated:
            raise InvalidDocumentError(
                "AI interview generator returned only unfounded experience "
                "questions while no candidate data was provided"
            )

        response.questions = validated
        response.total_questions = len(validated)
        return response