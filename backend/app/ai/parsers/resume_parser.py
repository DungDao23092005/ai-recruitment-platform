from __future__ import annotations

from app.ai.interfaces.base_provider import BaseLLMProvider
from app.ai.providers.gemini_provider import GeminiLLMProvider
from app.core.exceptions import EmptyDocumentError
from app.schemas.ai_resume import ParsedResumeSchema

RESUME_PARSER_SYSTEM_INSTRUCTION = """\
You are an expert AI Resume Parser. Your job is to accurately extract structured information from candidate CV text into the requested JSON schema.

Strict Extraction Rules:
1. Extract facts strictly present in the resume text. Do NOT hallucinate or assume unstated information.
2. Compute total_years_experience as a float based ONLY on explicit work experience timelines in the CV. If time periods overlap, do not double-count overlapping months/years. If data is insufficient or ambiguous, return null.
3. Preserve original technical and professional skill names (e.g., 'Python', 'FastAPI', 'React', 'Docker').
4. If optional fields (phone, email, title, summary, education, certifications, languages) are missing from the CV text, set them to null or empty lists as appropriate.
"""


class ResumeParser:
    """Structured Resume Parser using LLM Provider abstraction."""

    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or GeminiLLMProvider()

    async def parse(self, text: str) -> ParsedResumeSchema:
        """Parse raw resume text string into structured ParsedResumeSchema data.

        Args:
            text: Extracted plain text string of candidate CV.

        Returns:
            ParsedResumeSchema instance with extracted candidate information.

        Raises:
            EmptyDocumentError: If text input is empty or whitespace-only.
            InvalidDocumentError: If LLM generation or schema validation fails.
        """
        if not text or not text.strip():
            raise EmptyDocumentError("Resume text for parsing cannot be empty")

        prompt = f"""\
Extract structured candidate data from the following resume text:

--- RESUME TEXT ---
{text.strip()}
--- END RESUME TEXT ---
"""

        return await self.llm_provider.generate_structured_output(
            prompt=prompt,
            response_schema=ParsedResumeSchema,
            system_instruction=RESUME_PARSER_SYSTEM_INSTRUCTION,
        )
