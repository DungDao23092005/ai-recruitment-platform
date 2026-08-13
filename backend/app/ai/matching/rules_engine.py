from __future__ import annotations


class RulesEngine:
    """Pure skill and experience matching rules.

    Does not cover location or salary scoring.
    """

    def match_skills(
        self,
        candidate_skills: list[str],
        required_skills: list[str],
    ) -> list[str]:
        """Return candidate skills (original casing) that match required skills.

        Matching is case-insensitive. Candidate skills that have no exact
        required-skill counterpart are not included.
        """
        required_lower = {skill.lower() for skill in required_skills}
        return [
            skill
            for skill in candidate_skills
            if skill.lower() in required_lower
        ]

    def required_skill_coverage(
        self,
        required_skills: list[str],
        matching_skills: list[str],
    ) -> float:
        """Coverage of required skills by matching skills, in [0.0, 1.0].

        Preferred skills are intentionally excluded from this coverage.
        """
        if not required_skills:
            return 1.0

        matching_lower = {skill.lower() for skill in matching_skills}
        covered = sum(
            1 for skill in required_skills if skill.lower() in matching_lower
        )
        return covered / len(required_skills)

    def skill_gap(
        self,
        required_skills: list[str],
        matching_skills: list[str],
    ) -> list[str]:
        """Return required skills the candidate does not match."""
        matching_lower = {skill.lower() for skill in matching_skills}
        return [
            skill
            for skill in required_skills
            if skill.lower() not in matching_lower
        ]

    def experience_match(
        self,
        candidate_exp: float | None,
        minimum_exp: float | None,
    ) -> float:
        """Score candidate experience compatibility in [0.0, 1.0]."""
        if minimum_exp is None or minimum_exp <= 0:
            return 1.0

        if candidate_exp is None:
            return 0.5

        if candidate_exp >= minimum_exp:
            return 1.0

        score = candidate_exp / minimum_exp
        return max(0.0, min(1.0, score))
