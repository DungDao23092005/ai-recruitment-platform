from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_match import MatchResultSchema
from app.schemas.ai_resume import ParsedResumeSchema

QuestionCategory = Literal["technical", "behavioral", "experience", "skill_gap"]
QuestionDifficulty = Literal["easy", "medium", "hard"]


class GenerateInterviewQuestionsRequest(BaseModel):
    job: ParsedJobSchema = Field(
        description="Parsed job used as the grounding context for questions"
    )
    candidate: ParsedResumeSchema | None = Field(
        default=None,
        description="Optional parsed candidate resume for personalized questions",
    )
    match_result: MatchResultSchema | None = Field(
        default=None,
        description="Optional match result used to prioritize skill-gap questions",
    )
    num_questions: int = Field(
        default=5, ge=1, le=20, description="Number of questions to generate"
    )
    difficulty: Literal["easy", "medium", "hard", "mixed"] = Field(
        default="medium", description="Target difficulty of generated questions"
    )
    focus_areas: list[str] = Field(
        default_factory=list,
        description="Optional focus topics/skills to concentrate questions on",
    )


class InterviewQuestion(BaseModel):
    question: str = Field(description="The interview question text in Vietnamese")
    category: QuestionCategory = Field(
        description="Question category: technical, behavioral, experience, or skill_gap"
    )
    difficulty: QuestionDifficulty = Field(
        description="Question difficulty: easy, medium, or hard"
    )
    target_skill_or_topic: str = Field(
        description="The skill or topic this question targets"
    )
    evaluation_criteria: str = Field(
        description="What a good answer should demonstrate"
    )
    sample_answer_points: list[str] = Field(
        description="Key points a strong answer should include"
    )


class GenerateInterviewQuestionsResponse(BaseModel):
    job_title: str = Field(description="Title of the job the questions were built for")
    candidate_title: str | None = Field(
        default=None, description="Candidate professional title if candidate provided"
    )
    total_questions: int = Field(
        description="Number of generated interview questions"
    )
    questions: list[InterviewQuestion] = Field(
        description="The generated interview questions"
    )
