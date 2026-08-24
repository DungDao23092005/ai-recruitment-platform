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
from app.schemas.ai_resume import ParsedResumeSchema

_SYSTEM_INSTRUCTION = (
    "Bạn là một chuyên gia phỏng vấn tuyển dụng AI tài năng. Nhiệm vụ của bạn là tạo ra "
    "các câu hỏi phỏng vấn dựa trên Mô tả công việc (Job Description) và Sơ yếu lý "
    "lịch ứng viên (Candidate CV). \n"
    "1. Câu hỏi kỹ thuật (technical).\n"
    "2. Câu hỏi kinh nghiệm (experience).\n"
    "3. Câu hỏi dự án (project).\n"
    "4. Câu hỏi về kỹ năng còn thiếu (skill_gap).\n"
    "5. Câu hỏi hành vi (behavioral).\n"
    "Mỗi câu hỏi phải có lý do rõ ràng (reason) rút từ dữ kiện thực tế cung cấp (VD: 'Ứng viên có đề cập FastAPI trong dự án X.').\n"
    "Lưu ý: Nếu không có thông tin ứng viên, hãy chỉ tạo câu hỏi kỹ thuật và hành vi từ Job."
)

class InterviewGeneratorService:
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
    def _format_candidate_details(candidate: ParsedResumeSchema) -> str:
        lines = []
        if not candidate.experiences:
            lines.append("work_experience: (không có thông tin)")
        else:
            lines.append("work_experience:")
            for exp in candidate.experiences:
                period = f" ({exp.start_date or '?'} - {exp.end_date or 'Hiện tại'})"
                lines.append(f"- {exp.position} @ {exp.company}{period}")
                if exp.description:
                    lines.append(f"  description: {exp.description}")
                if exp.skills_used:
                    lines.append(f"  skills: {', '.join(exp.skills_used)}")

        if not candidate.projects:
            lines.append("projects: (không có thông tin)")
        else:
            lines.append("projects:")
            for proj in candidate.projects:
                lines.append(f"- {proj.name}")
                if proj.description:
                    lines.append(f"  description: {proj.description}")
                if proj.skills_used:
                    lines.append(f"  skills: {', '.join(proj.skills_used)}")

        return "\n".join(lines) + "\n"

    def build_prompt(self, request: GenerateInterviewQuestionsRequest) -> str:
        lines: list[str] = [
            "Dưới đây là dữ kiện đã cung cấp để tạo bộ câu hỏi phỏng vấn.",
            "",
            "--- JOB ---",
        ]
        job = request.job
        lines.append(f"title: {job.title or '(không cung cấp)'}")
        if job.summary:
            lines.append(f"summary: {job.summary}")
        lines.append(self._format_optional_list("required_skills", job.required_skills).rstrip())
        lines.append(self._format_optional_list("preferred_skills", job.preferred_skills).rstrip())
        if hasattr(job, 'responsibilities') and job.responsibilities:
            lines.append(self._format_optional_list("responsibilities", job.responsibilities).rstrip())
        lines.append(f"minimum_years_experience: {job.minimum_years_experience or '(không cung cấp)'}")

        lines.append("")
        lines.append("--- CANDIDATE ---")
        if request.candidate is None:
            lines.append("(thông tin ứng viên không được cung cấp)")
        else:
            candidate = request.candidate
            lines.append(f"title: {candidate.title or '(không cung cấp)'}")
            lines.append(f"total_years_experience: {candidate.total_years_experience or '(không cung cấp)'}")
            lines.append(self._format_optional_list("skills", candidate.skills).rstrip())
            lines.append(self._format_candidate_details(candidate).rstrip())

        lines.append("")
        lines.append("--- MATCH RESULT ---")
        if request.match_result is None:
            lines.append("(không có thông tin)")
        else:
            match_result = request.match_result
            lines.append(self._format_optional_list("matching_skills", match_result.matching_skills).rstrip())
            lines.append(self._format_optional_list("skill_gap", match_result.skill_gap).rstrip())

        lines.append("")
        lines.append("--- CONFIG ---")
        lines.append(f"num_questions: {request.num_questions}")
        lines.append(f"difficulty: {request.difficulty}")
        lines.append(self._format_optional_list("focus_areas", request.focus_areas).rstrip())

        return "\n".join(lines)

    async def generate_questions(
        self,
        request: GenerateInterviewQuestionsRequest,
    ) -> GenerateInterviewQuestionsResponse:
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
            raise InvalidDocumentError(f"AI interview generator provider failed: {exc}") from exc

        return self._validate_response(response, has_candidate=request.candidate is not None)

    @staticmethod
    def _require_job(job: ParsedJobSchema | None) -> None:
        if job is None:
            raise EmptyDocumentError("job is required")
        has_content = bool(
            job.title or job.summary or job.required_skills or job.preferred_skills or job.minimum_years_experience is not None
        )
        if not has_content:
            raise EmptyDocumentError("job has no content to generate questions from")

    @staticmethod
    def _validate_response(
        response: GenerateInterviewQuestionsResponse | None,
        has_candidate: bool,
    ) -> GenerateInterviewQuestionsResponse:
        if response is None:
            raise InvalidDocumentError("AI interview generator returned no response")
        if not response.job_title or not response.job_title.strip():
            raise InvalidDocumentError("AI interview generator returned an empty job_title")
        if not response.questions:
            raise InvalidDocumentError("AI interview generator returned no questions")

        validated: list[InterviewQuestion] = []
        for question in response.questions:
            if not question.question or not question.question.strip():
                raise InvalidDocumentError("AI interview generator returned an empty question")
            if not question.target_skill_or_topic or not question.target_skill_or_topic.strip():
                raise InvalidDocumentError("AI interview generator returned a question without target_skill_or_topic")
            if not question.evaluation_criteria or not question.evaluation_criteria.strip():
                raise InvalidDocumentError("AI interview generator returned a question without evaluation_criteria")
            if not getattr(question, 'reason', '').strip():
                raise InvalidDocumentError("AI interview generator returned a question without a reason")

            if not has_candidate and question.category in ("experience", "project", "skill_gap"):
                continue
            validated.append(question)

        if not validated:
            raise InvalidDocumentError("AI interview generator returned only unfounded questions while no candidate data was provided")

        response.questions = validated
        response.total_questions = len(validated)
        return response
