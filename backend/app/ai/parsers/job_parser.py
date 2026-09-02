from __future__ import annotations

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.ai.providers.gemini_provider import GeminiLLMProvider
from app.core.exceptions import EmptyDocumentError, InvalidDocumentError
from app.schemas.ai_job import ParsedJobSchema

JOB_PARSER_SYSTEM_INSTRUCTION = """\
You are an expert AI Job Description Parser. Your job is to accurately extract structured information from job description text into the requested JSON schema.

Strict Extraction Rules:
1. Extract only information strictly present in the job description text. Do NOT hallucinate or assume unstated requirements.
2. Preserve meaningful skill names exactly as written (e.g., 'Python', 'FastAPI', 'Docker', 'React').
3. Distinguish required vs preferred skills: if the JD does not clearly separate them, put clearly demanded skills into required_skills. Do NOT split a skill list in half.
4. Only put skills into preferred_skills if the JD explicitly marks them as preferred, nice-to-have, or optional.
5. Convert the experience requirement to a float (e.g. '3+ years' -> 3.0, 'at least 2 years' -> 2.0). If the JD does not mention experience, return null. Do NOT hallucinate a value.
6. Extract the required education degree/level, certifications, and languages only if the JD mentions it. Otherwise return null or empty lists.
7. Extract the seniority level (e.g., Junior, Mid, Senior, Lead, Manager) if mentioned.
8. Extract the key responsibilities into the responsibilities list.
9. Return null for unavailable scalar fields and [] for unavailable list fields.
10. Produce structured output matching ParsedJobSchema exactly.

Skill Name Constraints (CRITICAL):
- Each skill in required_skills and preferred_skills MUST be a concise technical term or keyword (maximum 3-4 words).
- Do NOT return full sentences, descriptions, paragraphs, or explanations as skill names.
- Do NOT include responsibilities or duties inside skill names.
- Extract only the core technology, tool, language, or methodology name.
- Example: "Docker" not "Hỗ trợ xây dựng và quản lý Docker containers và development environments"
- Example: "CI/CD" not "Tham gia xây dựng CI/CD pipeline và tự động hóa quy trình deployment"
- Example: "Linux" not "Làm việc với Linux"
"""


class JobParser:
    """Structured Job Description Parser using LLM Provider abstraction."""

    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or GeminiLLMProvider()

    async def parse(self, text: str) -> ParsedJobSchema:
        """Parse raw job description text string into structured ParsedJobSchema data.

        Args:
            text: Plain text string of the job description.

        Returns:
            ParsedJobSchema instance with extracted job information.

        Raises:
            EmptyDocumentError: If text input is empty or whitespace-only.
            InvalidDocumentError: If LLM generation or schema validation fails.
        """
        if not text or not text.strip():
            raise EmptyDocumentError(
                "Job description text for parsing cannot be empty"
            )

        prompt = f"""\
Extract structured job information from the following job description text:

--- JOB DESCRIPTION TEXT ---
{text.strip()}
--- END JOB DESCRIPTION TEXT ---
"""

        try:
            return await self.llm_provider.generate_structured_output(
                prompt=prompt,
                response_schema=ParsedJobSchema,
                system_instruction=JOB_PARSER_SYSTEM_INSTRUCTION,
            )
        except InvalidDocumentError:
            raise
        except Exception as exc:
            raise InvalidDocumentError(
                "Job description parsing failed due to LLM generation "
                "or schema validation error"
            ) from exc