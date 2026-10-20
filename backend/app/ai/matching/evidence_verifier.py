"""Deterministic evidence verification for explainable AI matching.

Feature 5 (Phase 1) requires that every piece of evidence shown to a recruiter
is a *verbatim* excerpt of the candidate's own ``Resume.parsed_data``. This
module is deliberately LLM-free and side-effect-free: it only locates claimed
text inside the resume and returns the original source substring.

Invariants enforced here:

* A quote is accepted only if it can be located (case-insensitively) inside the
  resume field/section it claims to come from. A match in an unrelated field is
  never accepted as proof.
* The returned ``quote`` is the exact substring from the resume, so the
  canonical casing/whitespace always comes from the source - never from the
  claim. Nothing is ever fabricated (no invented quote, index, date or
  duration).
* ``None`` / malformed parsed data is handled gracefully and simply yields no
  evidence.
* Absence of a quote is treated as "not evidenced in the provided CV" - it is
  never interpreted as proof that a skill is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.schemas.ai_explanation import EvidenceExcerpt
from app.schemas.ai_resume import (
    ParsedResumeSchema,
)

# Sections the verifier knows how to read. Anything else is denied, which keeps
# a hallucinated section name from silently matching a different field.
_KNOWN_SECTIONS = frozenset(
    {
        "skills",
        "job_titles",
        "summary",
        "title",
        "certifications",
        "languages",
        "experiences",
        "projects",
        "education",
    }
)


@dataclass(frozen=True)
class _Source:
    section: str
    field_name: str | None
    item_index: int | None
    item_title: str | None
    text: str


def _as_str_list(value: object) -> list[str]:
    """Return a clean list of strings from a possibly malformed value."""
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                result.append(stripped)
    return result


def _str_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _iter_education_field(edu: object) -> Iterable[tuple[str, str]]:
    for field_name in ("institution", "degree", "field_of_study"):
        text = _str_or_none(getattr(edu, field_name, None))
        if text is not None:
            yield field_name, text


class EvidenceVerifier:
    """Locate claimed evidence inside a parsed resume, deterministically."""

    def _iter_sources(
        self, parsed_resume: ParsedResumeSchema | None
    ) -> Iterable[_Source]:
        if parsed_resume is None:
            return

        for field_name in ("summary", "title"):
            text = _str_or_none(getattr(parsed_resume, field_name, None))
            if text is not None:
                yield _Source(field_name, field_name, None, None, text)

        for list_field in (
            "skills",
            "technical_skills",
            "soft_skills",
            "job_titles",
            "certifications",
            "languages",
        ):
            for index, text in enumerate(
                _as_str_list(getattr(parsed_resume, list_field, None))
            ):
                yield _Source(list_field, list_field, index, None, text)

        experiences = getattr(parsed_resume, "experiences", None)
        if isinstance(experiences, (list, tuple)):
            for index, exp in enumerate(experiences):
                title = _str_or_none(getattr(exp, "position", None)) or _str_or_none(
                    getattr(exp, "company", None)
                )
                for field_name in ("company", "position", "description"):
                    text = _str_or_none(getattr(exp, field_name, None))
                    if text is not None:
                        yield _Source(
                            "experiences", field_name, index, title, text
                        )
                for skill in _as_str_list(getattr(exp, "skills_used", None)):
                    yield _Source(
                        "experiences", "skills_used", index, title, skill
                    )

        projects = getattr(parsed_resume, "projects", None)
        if isinstance(projects, (list, tuple)):
            for index, proj in enumerate(projects):
                name = _str_or_none(getattr(proj, "name", None))
                for field_name in ("name", "description"):
                    text = _str_or_none(getattr(proj, field_name, None))
                    if text is not None:
                        yield _Source("projects", field_name, index, name, text)
                for skill in _as_str_list(getattr(proj, "skills_used", None)):
                    yield _Source("projects", "skills_used", index, name, skill)

        education = getattr(parsed_resume, "education", None)
        if isinstance(education, (list, tuple)):
            for index, edu in enumerate(education):
                institution = _str_or_none(getattr(edu, "institution", None))
                for field_name, text in _iter_education_field(edu):
                    yield _Source(
                        "education", field_name, index, institution, text
                    )

    def _match_in_source(self, source: _Source, needle_lower: str) -> str | None:
        haystack_lower = source.text.lower()
        position = haystack_lower.find(needle_lower)
        if position < 0:
            return None
        return source.text[position : position + len(needle_lower)]

    def find(
        self,
        parsed_resume: ParsedResumeSchema | None,
        section: str | None,
        quote: str | None,
        field_name: str | None = None,
        item_index: int | None = None,
    ) -> EvidenceExcerpt | None:
        """Return verified evidence, or ``None`` when the quote is unsupported.

        The claimed ``section`` is the trust boundary: a quote that only appears
        in a different section is rejected. When ``field_name`` / ``item_index``
        are supplied but do not contain the quote, the verifier still tolerates
        a correct quote elsewhere in the *same* section and reports its true
        location, so imperfect provenance metadata cannot hide real evidence.
        """
        if parsed_resume is None or section not in _KNOWN_SECTIONS:
            return None
        if not isinstance(quote, str):
            return None
        stripped_quote = quote.strip()
        if not stripped_quote:
            return None
        needle_lower = stripped_quote.lower()

        section_sources = [
            source
            for source in self._iter_sources(parsed_resume)
            if source.section == section
        ]

        candidates: list[_Source] = section_sources
        if field_name is not None or item_index is not None:
            narrowed = [
                source
                for source in section_sources
                if (field_name is None or source.field_name == field_name)
                and (item_index is None or source.item_index == item_index)
            ]
            candidates = narrowed + [
                source for source in section_sources if source not in narrowed
            ]

        for source in candidates:
            canonical = self._match_in_source(source, needle_lower)
            if canonical is not None:
                return EvidenceExcerpt(
                    section=source.section,
                    field_name=source.field_name,
                    item_index=source.item_index,
                    item_title=source.item_title,
                    quote=canonical,
                )
        return None

    def verify(
        self,
        parsed_resume: ParsedResumeSchema | None,
        excerpt: EvidenceExcerpt,
    ) -> EvidenceExcerpt | None:
        """Verify a single claimed excerpt against the resume."""
        return self.find(
            parsed_resume,
            section=excerpt.section,
            quote=excerpt.quote,
            field_name=excerpt.field_name,
            item_index=excerpt.item_index,
        )

    def verify_all(
        self,
        parsed_resume: ParsedResumeSchema | None,
        excerpts: Iterable[EvidenceExcerpt],
    ) -> list[EvidenceExcerpt]:
        """Verify a batch, dropping every unverifiable claim."""
        verified: list[EvidenceExcerpt] = []
        for excerpt in excerpts:
            result = self.verify(parsed_resume, excerpt)
            if result is not None:
                verified.append(result)
        return verified
