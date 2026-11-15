from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from scripts import seed_company_free_plan as seeder
from scripts.seed_company_free_plan import (
    CompanyFreePlanConfig,
    SeedError,
    SeedResult,
    load_config,
)


def _config() -> CompanyFreePlanConfig:
    return CompanyFreePlanConfig(
        name="Test-only Company Free Plan",
        description="Test-only fixture values; not a production plan.",
        price=0,
        currency="VND",
        duration_days=30,
        max_job_posts=1,
        max_candidate_searches=10,
        max_ai_features=5,
        plan_audience="company",
        is_free=True,
    )


def _install(
    monkeypatch,
    *,
    result: SeedResult | None = None,
    error: Exception | None = None,
    dispose_error: Exception | None = None,
) -> tuple[AsyncMock, AsyncMock]:
    seed = AsyncMock(return_value=result, side_effect=error)
    dispose = AsyncMock(side_effect=dispose_error)
    monkeypatch.setattr(seeder, "seed_company_free_plan", seed)
    monkeypatch.setattr(seeder, "engine", SimpleNamespace(dispose=dispose))
    return seed, dispose


def test_canonical_config_file_has_approved_company_free_values():
    config_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "company_free_plan.json"
    )
    config = load_config(config_path)

    assert config.plan_audience.value == "company"
    assert config.is_free is True
    assert config.price == 0
    assert config.currency == "VND"
    assert config.duration_days == 30
    assert config.max_job_posts == 1
    assert config.max_candidate_searches == 10
    assert config.max_ai_features == 5


def test_config_rejects_non_company_free_plan():
    with pytest.raises(ValueError):
        CompanyFreePlanConfig(
            name="n",
            description="d",
            price=0,
            currency="VND",
            duration_days=30,
            max_job_posts=1,
            max_candidate_searches=10,
            max_ai_features=5,
            plan_audience="candidate",
            is_free=True,
        )


def test_config_rejects_paid_price():
    with pytest.raises(ValueError):
        CompanyFreePlanConfig(
            name="n",
            description="d",
            price=1000,
            currency="VND",
            duration_days=30,
            max_job_posts=1,
            max_candidate_searches=10,
            max_ai_features=5,
            plan_audience="company",
            is_free=True,
        )


@pytest.mark.asyncio
async def test_run_cli_disposes_engine_after_dry_run(monkeypatch):
    config = _config()
    result = SeedResult(
        action="would-insert", plan_id=None, message="[DRY RUN] would create"
    )
    seed, dispose = _install(monkeypatch, result=result)

    actual = await seeder._run_cli(config, apply=False)

    assert actual is result
    seed.assert_awaited_once_with(config, apply=False)
    dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_cli_disposes_engine_on_no_op(monkeypatch):
    plan_id = uuid4()
    result = SeedResult(
        action="no-op", plan_id=plan_id, message="[OK] already exists"
    )
    seed, dispose = _install(monkeypatch, result=result)

    actual = await seeder._run_cli(None, apply=True)

    assert actual is result
    seed.assert_awaited_once_with(None, apply=True)
    dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_cli_disposes_engine_when_seeder_raises(monkeypatch):
    seed, dispose = _install(monkeypatch, error=SeedError("seeder failed"))

    with pytest.raises(SeedError, match="seeder failed"):
        await seeder._run_cli(None, apply=True)

    seed.assert_awaited_once_with(None, apply=True)
    dispose.assert_awaited_once_with()


def test_main_runs_cli_wrapper(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "company_free_plan.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "Test-only Company Free Plan",
                "description": "Test-only fixture values; not a production plan.",
                "price": 0,
                "currency": "VND",
                "duration_days": 30,
                "max_job_posts": 1,
                "max_candidate_searches": 10,
                "max_ai_features": 5,
                "plan_audience": "company",
                "is_free": True,
            }
        ),
        encoding="utf-8",
    )
    result = SeedResult(
        action="would-insert", plan_id=None, message="[DRY RUN] would create"
    )
    seen: dict[str, object] = {}

    async def fake_run_cli(config, *, apply):
        seen["config"] = config
        seen["apply"] = apply
        return result

    monkeypatch.setattr(seeder, "_run_cli", fake_run_cli)

    seeder.main(["--config", str(config_path)])

    assert seen["apply"] is False
    assert isinstance(seen["config"], CompanyFreePlanConfig)
    assert result.message in capsys.readouterr().out
