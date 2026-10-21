from __future__ import annotations

import uuid
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import settings
from app.core.rate_limit import (
    EXPLANATION_REFRESH_ENDPOINT,
    RateLimiter,
    explanation_refresh_rate_limit,
    set_rate_limiter,
)
from app.domain.enums import UserRole
from app.models import User


class FakeRateLimiter:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = defaultdict(int)
        self.calls: list[tuple[str, str, int, int]] = []

    async def check_limit(
        self,
        *,
        endpoint: str,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
        fail_closed: bool = False,
    ):
        self.calls.append((endpoint, identifier, limit, window_seconds))
        key = (endpoint, identifier)
        self.counts[key] += 1
        current = self.counts[key]
        from app.core.rate_limit import RateLimitResult

        return RateLimitResult(
            allowed=current <= limit,
            current_count=current,
            ttl_remaining=60,
            reset_time=0.0,
            limit=limit,
            remaining=max(0, limit - current),
        )


class FakeDb:
    def __init__(self, company_id: uuid.UUID | None = None) -> None:
        self.company_id = company_id

    async def scalar(self, _statement):
        return self.company_id


def make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.RECRUITER,
        is_active=True,
    )


@pytest.fixture(autouse=True)
def restore_limiter():
    yield
    set_rate_limiter(None)


@pytest.fixture
def enabled_limiter(monkeypatch) -> FakeRateLimiter:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(
        settings, "RATE_LIMIT_EXPLANATION_REFRESH_PER_MINUTE", 30
    )
    limiter = FakeRateLimiter()
    set_rate_limiter(limiter)
    return limiter


async def test_31st_refresh_for_a_tenant_is_rejected(enabled_limiter) -> None:
    user = make_user()
    company_id = uuid.uuid4()

    for _ in range(30):
        result = await explanation_refresh_rate_limit(
            current_user=user, db=FakeDb(company_id)
        )
        assert result.allowed

    with pytest.raises(HTTPException) as exc_info:
        await explanation_refresh_rate_limit(
            current_user=user, db=FakeDb(company_id)
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "60"}
    assert enabled_limiter.calls[0][0] == EXPLANATION_REFRESH_ENDPOINT
    assert enabled_limiter.calls[0][2] == 30


async def test_recruiters_in_the_same_company_share_one_bucket(
    enabled_limiter,
) -> None:
    company_id = uuid.uuid4()
    first = make_user()
    second = make_user()

    for _ in range(15):
        await explanation_refresh_rate_limit(
            current_user=first, db=FakeDb(company_id)
        )
    for _ in range(15):
        await explanation_refresh_rate_limit(
            current_user=second, db=FakeDb(company_id)
        )

    with pytest.raises(HTTPException) as exc_info:
        await explanation_refresh_rate_limit(
            current_user=second, db=FakeDb(company_id)
        )

    assert exc_info.value.status_code == 429
    assert {call[1] for call in enabled_limiter.calls} == {
        f"company:{company_id}"
    }


async def test_different_companies_have_independent_buckets(
    enabled_limiter,
) -> None:
    first = make_user()
    second = make_user()
    first_company = uuid.uuid4()
    second_company = uuid.uuid4()

    for _ in range(30):
        await explanation_refresh_rate_limit(
            current_user=first, db=FakeDb(first_company)
        )
    result = await explanation_refresh_rate_limit(
        current_user=second, db=FakeDb(second_company)
    )

    assert result.allowed
    assert result.current_count == 1


async def test_user_without_company_is_bucketed_by_user_id(
    enabled_limiter,
) -> None:
    user = make_user()

    await explanation_refresh_rate_limit(current_user=user, db=FakeDb())

    assert enabled_limiter.calls[0][1] == f"user:{user.id}"


async def test_disabled_rate_limit_allows_without_touching_redis(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    limiter = FakeRateLimiter()
    set_rate_limiter(limiter)

    result = await explanation_refresh_rate_limit(
        current_user=make_user(), db=FakeDb()
    )

    assert result.allowed
    assert limiter.calls == []


async def test_missing_limiter_allows_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    set_rate_limiter(None)

    result = await explanation_refresh_rate_limit(
        current_user=make_user(), db=FakeDb()
    )

    assert result.allowed


async def test_redis_outage_fails_open(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    redis_client = MagicMock()
    redis_client.register_script.return_value = AsyncMock(
        side_effect=RedisConnectionError("redis unavailable")
    )
    set_rate_limiter(RateLimiter(redis_client))

    result = await explanation_refresh_rate_limit(
        current_user=make_user(), db=FakeDb()
    )

    assert result.allowed
