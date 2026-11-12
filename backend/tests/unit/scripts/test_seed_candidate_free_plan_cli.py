from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from scripts import seed_candidate_free_plan as seeder
from scripts.seed_candidate_free_plan import (
    CandidateFreePlanConfig,
    SeedError,
    SeedResult,
)


def _config() -> CandidateFreePlanConfig:
    return CandidateFreePlanConfig(
        name="Test-only Candidate Free Plan",
        description="Test-only fixture values; not a production plan.",
        price=0,
        currency="VND",
        duration_days=30,
        max_job_posts=0,
        max_candidate_searches=0,
        max_ai_features=0,
        plan_audience="candidate",
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
    monkeypatch.setattr(seeder, "seed_candidate_free_plan", seed)
    monkeypatch.setattr(seeder, "engine", SimpleNamespace(dispose=dispose))
    return seed, dispose


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
async def test_run_cli_disposes_engine_after_successful_apply(monkeypatch):
    config = _config()
    result = SeedResult(
        action="inserted", plan_id=uuid4(), message="[OK] created"
    )
    seed, dispose = _install(monkeypatch, result=result)

    actual = await seeder._run_cli(config, apply=True)

    assert actual is result
    seed.assert_awaited_once_with(config, apply=True)
    dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_cli_disposes_engine_when_seeder_raises(monkeypatch):
    seed, dispose = _install(monkeypatch, error=SeedError("seeder failed"))

    with pytest.raises(SeedError, match="seeder failed"):
        await seeder._run_cli(None, apply=True)

    seed.assert_awaited_once_with(None, apply=True)
    dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_cleanup_error_does_not_mask_original_seeder_error(monkeypatch):
    _seed, dispose = _install(
        monkeypatch,
        error=SeedError("original seeder failure"),
        dispose_error=RuntimeError("engine dispose failed"),
    )

    with pytest.raises(SeedError, match="original seeder failure"):
        await seeder._run_cli(None, apply=True)

    dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_cleanup_error_propagates_after_success(monkeypatch):
    result = SeedResult(
        action="would-insert", plan_id=None, message="[DRY RUN] would create"
    )
    _seed, dispose = _install(
        monkeypatch,
        result=result,
        dispose_error=RuntimeError("engine dispose failed"),
    )

    with pytest.raises(RuntimeError, match="engine dispose failed"):
        await seeder._run_cli(None, apply=False)

    dispose.assert_awaited_once_with()


def test_main_runs_cli_wrapper(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "candidate_free_plan.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "Test-only Candidate Free Plan",
                "description": "Test-only fixture values; not a production plan.",
                "price": 0,
                "currency": "VND",
                "duration_days": 30,
                "max_job_posts": 0,
                "max_candidate_searches": 0,
                "max_ai_features": 0,
                "plan_audience": "candidate",
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
    assert isinstance(seen["config"], CandidateFreePlanConfig)
    assert result.message in capsys.readouterr().out
