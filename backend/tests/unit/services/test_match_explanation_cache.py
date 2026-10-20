from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.ai_explanation import (
    ApplicationMatchExplanationResponse,
    EvidenceExcerpt,
    ScoreBreakdown,
    SkillEvaluation,
)
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema, WorkExperienceSchema
from app.services.match_explanation_cache import (
    CacheSerializationError,
    MatchExplanationCache,
    canonical_json_bytes,
    content_hash,
)

GENERATED_AT = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)


class FakeRedis:
    def __init__(
        self,
        values: dict[str, str | bytes] | None = None,
        *,
        get_error: Exception | None = None,
        set_error: Exception | None = None,
    ) -> None:
        self.values = dict(values or {})
        self.get_error = get_error
        self.set_error = set_error
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str):
        self.get_calls.append(key)
        if self.get_error is not None:
            raise self.get_error
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.set_calls.append((key, value, ex))
        if self.set_error is not None:
            raise self.set_error
        self.values[key] = value
        return True


def make_resume(**overrides) -> ParsedResumeSchema:
    values = {
        "full_name": "Nguyễn Văn An",
        "title": "Backend Engineer",
        "summary": "Kỹ sư phần mềm với 5 năm kinh nghiệm.",
        "total_years_experience": 5.0,
        "skills": ["Python", "FastAPI"],
        "experiences": [
            WorkExperienceSchema(
                company="Acme",
                position="Engineer",
                start_date="2019",
                end_date="2024",
                description="Xây dựng hệ thống.",
                skills_used=["Python"],
            )
        ],
    }
    values.update(overrides)
    return ParsedResumeSchema(**values)


def make_job(**overrides) -> ParsedJobSchema:
    values = {
        "title": "Backend Engineer",
        "summary": "Xây dựng API.",
        "required_skills": ["Python", "Docker"],
        "preferred_skills": ["GraphQL"],
        "minimum_years_experience": 3.0,
        "education_level": "Bachelor",
    }
    values.update(overrides)
    return ParsedJobSchema(**values)


def make_response(
    application_id: uuid.UUID | None = None,
    **overrides,
) -> ApplicationMatchExplanationResponse:
    values = {
        "application_id": application_id or uuid.uuid4(),
        "overall_score": 77.5,
        "score_breakdown": ScoreBreakdown(
            overall_score=77.5,
            cosine_similarity=0.71,
            skill_coverage_score=0.5,
            preferred_skill_coverage_score=0.0,
            experience_match_score=1.0,
            education_score=0.5,
            project_score=0.4,
        ),
        "summary": "Deterministic match score 77.50/100.",
        "summary_source": "deterministic",
        "skill_evaluations": [
            SkillEvaluation(
                skill_name="Python",
                requirement_type="required",
                status="matched_evidenced",
                explanation="Listed in skills.",
                evidence=[
                    EvidenceExcerpt(
                        section="skills",
                        field_name="skills",
                        item_index=0,
                        quote="Python",
                    )
                ],
            )
        ],
        "generated_at": GENERATED_AT,
        "cache_state": "not_cached",
    }
    values.update(overrides)
    return ApplicationMatchExplanationResponse(**values)


def make_cache(redis, **overrides) -> MatchExplanationCache:
    values = {
        "enabled": True,
        "ttl_seconds": 604800,
        "version": "v1",
    }
    values.update(overrides)
    return MatchExplanationCache(redis, **values)


def test_dict_key_order_produces_identical_hashes():
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})


def test_nested_unicode_text_is_stable():
    first = {"skills": ["Lập trình", {"name": "Kỹ sư"}], "note": "Tiếng Việt"}
    second = {"note": "Tiếng Việt", "skills": ["Lập trình", {"name": "Kỹ sư"}]}

    assert content_hash(first) == content_hash(second)
    assert content_hash(first) != content_hash(
        {"skills": ["Lập trình"], "note": "Tiếng Việt"}
    )
    assert "Lập trình".encode("utf-8") in canonical_json_bytes(first)


def test_primitives_serialize_predictably():
    assert content_hash(True) != content_hash(1)
    assert content_hash(1) != content_hash(1.0)
    assert content_hash(None) == content_hash(None)
    assert content_hash([1, None, False]) != content_hash([1, None, True])


@pytest.mark.parametrize("value", [object(), {1: "x"}, {1, 2}, b"bytes"])
def test_unsupported_values_are_rejected(value):
    with pytest.raises(CacheSerializationError):
        content_hash(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_rejected(value):
    with pytest.raises(CacheSerializationError):
        content_hash(value)


def test_resume_content_change_produces_new_key():
    cache = make_cache(FakeRedis())
    application_id = uuid.uuid4()

    key_a = cache.build_key(application_id, make_resume(), make_job())
    key_b = cache.build_key(
        application_id, make_resume(skills=["Python", "Django"]), make_job()
    )

    assert key_a is not None
    assert key_b is not None
    assert key_a != key_b


def test_job_requirements_or_description_change_produces_new_key():
    cache = make_cache(FakeRedis())
    application_id = uuid.uuid4()

    base = cache.build_key(application_id, make_resume(), make_job())
    changed_skills = cache.build_key(
        application_id, make_resume(), make_job(required_skills=["Go"])
    )
    changed_summary = cache.build_key(
        application_id, make_resume(), make_job(summary="Different description")
    )

    assert base is not None
    assert changed_skills is not None and changed_skills != base
    assert changed_summary is not None and changed_summary != base


def test_version_change_produces_new_key():
    redis = FakeRedis()
    application_id = uuid.uuid4()

    key_v1 = make_cache(redis, version="v1").build_key(
        application_id, make_resume(), make_job()
    )
    key_v2 = make_cache(redis, version="v2").build_key(
        application_id, make_resume(), make_job()
    )

    assert key_v1 is not None and key_v2 is not None
    assert key_v1 != key_v2


def test_different_applications_produce_distinct_keys():
    cache = make_cache(FakeRedis())
    resume = make_resume()
    job = make_job()

    key_a = cache.build_key(uuid.uuid4(), resume, job)
    key_b = cache.build_key(uuid.uuid4(), resume, job)

    assert key_a is not None and key_b is not None
    assert key_a != key_b


def test_key_contains_prefix_application_and_version():
    cache = make_cache(FakeRedis(), version="v9")
    application_id = uuid.uuid4()

    key = cache.build_key(application_id, make_resume(), make_job())

    assert key is not None
    assert key.startswith(f"match_explanation:{application_id}:")
    assert key.endswith(":v9")
    assert key.count(":") == 4


def test_missing_parsed_data_bypasses_hashing():
    cache = make_cache(FakeRedis())

    assert cache.build_key(uuid.uuid4(), None, make_job()) is None
    assert cache.build_key(uuid.uuid4(), make_resume(), None) is None
    assert cache.build_key(uuid.uuid4(), object(), make_job()) is None


def test_miss_returns_none():
    redis = FakeRedis()
    cache = make_cache(redis)

    result = asyncio.run(cache.get("missing", application_id="app"))

    assert result is None
    assert redis.get_calls == ["missing"]


def test_hit_preserves_metadata_and_updates_cache_state():
    application_id = uuid.uuid4()
    response = make_response(
        application_id,
        summary_source="ai_generated",
        model_version="gemini-test",
        cache_state="not_cached",
    )
    key = "cached-key"
    redis = FakeRedis(
        {key: json.dumps(response.model_dump(mode="json"))}
    )
    cache = make_cache(redis)

    result = asyncio.run(cache.get(key, application_id=application_id))

    assert result is not None
    assert result.cache_state == "cached"
    assert result.summary_source == "ai_generated"
    assert result.model_version == "gemini-test"
    assert result.generated_at == GENERATED_AT
    assert result.overall_score == 77.5
    assert result.evidence == response.evidence


def test_store_writes_json_with_ttl_and_preserves_content():
    application_id = uuid.uuid4()
    response = make_response(
        application_id, summary="Kết quả khớp 77.50/100."
    )
    redis = FakeRedis()
    cache = make_cache(redis, ttl_seconds=123)
    key = cache.build_key(application_id, make_resume(), make_job())
    assert key is not None

    stored = asyncio.run(
        cache.store(key, response, application_id=application_id)
    )

    assert stored is True
    assert len(redis.set_calls) == 1
    set_key, text, ttl = redis.set_calls[0]
    assert set_key == key
    assert ttl == 123
    payload = json.loads(text)
    assert payload["application_id"] == str(application_id)
    assert payload["summary_source"] == "deterministic"
    assert payload["cache_state"] == "not_cached"
    assert "Kết quả khớp" in text


def test_corrupt_json_is_a_cache_miss():
    redis = FakeRedis({"key": "{not-json"})
    cache = make_cache(redis)

    assert asyncio.run(cache.get("key")) is None


def test_schema_incompatible_payload_is_a_cache_miss():
    redis = FakeRedis({"key": json.dumps({"application_id": str(uuid.uuid4())})})
    cache = make_cache(redis)

    assert asyncio.run(cache.get("key")) is None


def test_cache_get_failure_degrades():
    redis = FakeRedis(get_error=ConnectionError("redis down"))
    cache = make_cache(redis)

    assert asyncio.run(cache.get("key")) is None


def test_cache_set_failure_degrades():
    redis = FakeRedis(set_error=TimeoutError("timeout"))
    cache = make_cache(redis)
    response = make_response()

    assert (
        asyncio.run(cache.store("key", response, application_id="a"))
        is False
    )


def test_disabled_cache_bypasses_all_redis_operations():
    redis = FakeRedis()
    cache = make_cache(redis, enabled=False)

    assert asyncio.run(cache.get("key")) is None
    assert (
        asyncio.run(cache.store("key", make_response())) is False
    )
    assert redis.get_calls == []
    assert redis.set_calls == []


def test_missing_redis_client_bypasses_all_operations():
    cache = make_cache(None)

    assert asyncio.run(cache.get("key")) is None
    assert (
        asyncio.run(cache.store("key", make_response())) is False
    )


@pytest.mark.parametrize("ttl", [0, -1])
def test_invalid_cache_ttl_is_rejected(ttl):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, MATCH_EXPLANATION_CACHE_TTL_SECONDS=ttl)


@pytest.mark.parametrize("version", ["", " ", "v1:bad", "x" * 65])
def test_invalid_cache_version_is_rejected(version):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, MATCH_EXPLANATION_CACHE_VERSION=version)


def test_valid_cache_settings_defaults():
    config = Settings(_env_file=None)

    assert config.MATCH_EXPLANATION_CACHE_ENABLED is True
    assert config.MATCH_EXPLANATION_CACHE_TTL_SECONDS == 604800
    assert config.MATCH_EXPLANATION_CACHE_VERSION == "v1"
