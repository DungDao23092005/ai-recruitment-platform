from __future__ import annotations


class RulesEngine:
    """Pure skill, experience, education, and project matching rules."""

    def match_skills(
        self,
        candidate_skills: list[str],
        target_skills: list[str],
    ) -> list[str]:
        """Return candidate skills (original casing) that match target skills.

        Matching is case-insensitive.
        """
        target_lower = {skill.lower() for skill in target_skills}
        return [
            skill
            for skill in candidate_skills
            if skill.lower() in target_lower
        ]

    def skill_coverage(
        self,
        target_skills: list[str],
        matching_skills: list[str],
    ) -> float:
        """Coverage of target skills by matching skills, in [0.0, 1.0]."""
        if not target_skills:
            return 1.0

        matching_lower = {skill.lower() for skill in matching_skills}
        covered = sum(
            1 for skill in target_skills if skill.lower() in matching_lower
        )
        return covered / len(target_skills)

    def skill_gap(
        self,
        target_skills: list[str],
        matching_skills: list[str],
    ) -> list[str]:
        """Return target skills the candidate does not match."""
        matching_lower = {skill.lower() for skill in matching_skills}
        return [
            skill
            for skill in target_skills
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

    def education_match(
        self,
        candidate_education: list,
        required_education: str | None,
    ) -> float:
        """Score candidate education against required degree level in [0.0, 1.0].

        Simple heuristic matching based on common degree keywords.
        """
        if not required_education:
            return 1.0

        if not candidate_education:
            return 0.0

        req_lower = required_education.lower()

        # Rank education levels
        levels = {"high school": 1, "associate": 2, "bachelor": 3, "master": 4, "phd": 5, "doctorate": 5}

        req_level = 0
        for key, val in levels.items():
            if key in req_lower:
                req_level = val
                break

        if req_level == 0:
            # Cannot determine requirement, assume okay if they have any education
            return 0.8

        max_cand_level = 0
        for edu in candidate_education:
            degree = getattr(edu, "degree", "") or ""
            degree = degree.lower()
            for key, val in levels.items():
                if key in degree and val > max_cand_level:
                    max_cand_level = val

        if max_cand_level >= req_level:
            return 1.0
        elif max_cand_level == req_level - 1:
            return 0.5
        else:
            return 0.0

    def project_relevance(
        self,
        candidate_projects: list,
        required_skills: list[str],
    ) -> float:
        """Score candidate projects based on usage of required skills.

        Returns a score in [0.0, 1.0].
        """
        if not required_skills:
            return 1.0

        if not candidate_projects:
            return 0.0

        req_lower = {s.lower() for s in required_skills}

        total_project_skills = set()
        for proj in candidate_projects:
            skills = getattr(proj, "skills_used", []) or []
            total_project_skills.update(s.lower() for s in skills)

        covered = len(req_lower.intersection(total_project_skills))
        if covered == 0:
            return 0.2  # They have projects but not related to required skills

        coverage = covered / len(req_lower)
        # Having some relevant projects is good, we don't expect projects to cover ALL skills
        return min(1.0, coverage * 2.0)
