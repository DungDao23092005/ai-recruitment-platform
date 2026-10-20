from __future__ import annotations

from app.ai.matching.evidence_verifier import EvidenceVerifier
from app.schemas.ai_explanation import EvidenceExcerpt
from app.schemas.ai_resume import (
    EducationSchema,
    ParsedResumeSchema,
    ProjectSchema,
    WorkExperienceSchema,
)


def make_resume() -> ParsedResumeSchema:
    return ParsedResumeSchema(
        full_name="Jane Doe",
        title="Senior Python Engineer",
        summary="Backend specialist with 8 years of experience.",
        skills=["Python", "FastAPI", "SQL"],
        technical_skills=["Docker"],
        job_titles=["Backend Engineer"],
        experiences=[
            WorkExperienceSchema(
                company="Acme",
                position="Backend Engineer",
                start_date="2019",
                end_date="2022",
                description="Built Python microservices with FastAPI.",
                skills_used=["Python", "FastAPI"],
            )
        ],
        projects=[
            ProjectSchema(
                name="Data Pipeline",
                description="Streaming platform using Kafka.",
                skills_used=["Kafka", "Python"],
            )
        ],
        education=[
            EducationSchema(
                institution="HUST",
                degree="Bachelor of Science",
                field_of_study="Computer Science",
            )
        ],
    )


class TestEvidenceVerifierFind:
    def test_exact_skill_match_returns_canonical_quote(self):
        verifier = EvidenceVerifier()

        result = verifier.find(make_resume(), "skills", "Python")

        assert result is not None
        assert result.section == "skills"
        assert result.quote == "Python"
        assert result.field_name == "skills"

    def test_case_insensitive_match_returns_source_casing(self):
        verifier = EvidenceVerifier()

        result = verifier.find(make_resume(), "skills", "python")

        assert result is not None
        assert result.quote == "Python"

    def test_substring_inside_description_is_verified(self):
        verifier = EvidenceVerifier()

        result = verifier.find(
            make_resume(), "experiences", "Python microservices"
        )

        assert result is not None
        assert result.quote == "Python microservices"
        assert result.field_name == "description"
        assert result.item_index == 0

    def test_experience_item_title_uses_role_position(self):
        verifier = EvidenceVerifier()

        result = verifier.find(
            make_resume(), "experiences", "FastAPI", field_name="skills_used"
        )

        assert result is not None
        assert result.item_index == 0
        assert result.item_title == "Backend Engineer"

    def test_project_evidence_verified(self):
        verifier = EvidenceVerifier()

        result = verifier.find(make_resume(), "projects", "Kafka")

        assert result is not None
        assert result.section == "projects"
        assert result.item_title == "Data Pipeline"

    def test_quote_in_wrong_section_is_rejected(self):
        verifier = EvidenceVerifier()

        # "Python" exists only in the resume skills, never claimed as education.
        result = verifier.find(make_resume(), "education", "Python")

        assert result is None

    def test_unknown_section_is_rejected(self):
        verifier = EvidenceVerifier()

        result = verifier.find(make_resume(), "hobbies", "Python")

        assert result is None

    def test_fabricated_quote_is_rejected(self):
        verifier = EvidenceVerifier()

        result = verifier.find(make_resume(), "skills", "Rust")

        assert result is None

    def test_wrong_metadata_still_finds_real_section_evidence(self):
        verifier = EvidenceVerifier()

        # Claimed index 5 does not exist; the quote still exists in section 0.
        result = verifier.find(
            make_resume(), "experiences", "FastAPI", item_index=5
        )

        assert result is not None
        assert result.item_index == 0
        assert result.quote == "FastAPI"

    def test_empty_quote_rejected(self):
        verifier = EvidenceVerifier()

        assert verifier.find(make_resume(), "skills", "   ") is None
        assert verifier.find(make_resume(), "skills", "") is None

    def test_none_resume_returns_none(self):
        verifier = EvidenceVerifier()

        assert verifier.find(None, "skills", "Python") is None

    def test_none_section_returns_none(self):
        verifier = EvidenceVerifier()

        assert verifier.find(make_resume(), None, "Python") is None


class TestEvidenceVerifierRobustness:
    def test_malformed_parsed_resume_is_handled(self):
        verifier = EvidenceVerifier()
        resume = ParsedResumeSchema(skills=["Python"])
        # Simulate corrupt data that bypassed validation.
        object.__setattr__(resume, "experiences", "not-a-list")
        object.__setattr__(resume, "skills", "not-a-list")

        # Must not raise; skills is now malformed so it yields no evidence.
        assert verifier.find(resume, "skills", "Python") is None

    def test_verify_all_drops_unverifiable_claims(self):
        verifier = EvidenceVerifier()
        claims = [
            EvidenceExcerpt(section="skills", quote="Python"),
            EvidenceExcerpt(section="skills", quote="Rust"),
            EvidenceExcerpt(section="experiences", quote="Python microservices"),
        ]

        verified = verifier.verify_all(make_resume(), claims)

        assert [evidence.quote for evidence in verified] == [
            "Python",
            "Python microservices",
        ]

    def test_verify_uses_true_source_text_not_claim_casing(self):
        verifier = EvidenceVerifier()
        claim = EvidenceExcerpt(section="skills", quote="FASTAPI")

        verified = verifier.verify(make_resume(), claim)

        assert verified is not None
        assert verified.quote == "FastAPI"
