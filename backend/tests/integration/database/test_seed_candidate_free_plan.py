from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.database.session import async_session_factory
from app.domain.enums import PlanAudience
from app.models import RecruitmentPlan
from scripts.seed_candidate_free_plan import (
    CandidateFreePlanConfig,
    SeedError,
    classify_candidate_free_plans,
    load_config,
    seed_candidate_free_plan,
)


def make_config(**overrides) -> CandidateFreePlanConfig:
    values = {
        "name": "Test-only Candidate Free Plan",
        "description": "Test-only fixture values; not a production plan.",
        "price": 0,
        "currency": "vnd",
        "duration_days": 30,
        "max_job_posts": 0,
        "max_candidate_searches": 0,
        "max_ai_features": 0,
        "plan_audience": PlanAudience.CANDIDATE,
        "is_free": True,
    }
    values.update(overrides)
    return CandidateFreePlanConfig(**values)


async def _load_all_plans() -> list[RecruitmentPlan]:
    async with async_session_factory() as session:
        result = await session.execute(select(RecruitmentPlan))
        return list(result.scalars().all())


async def _insert_plan(*, is_active: bool, is_deleted: bool) -> RecruitmentPlan:
    async with async_session_factory() as session:
        plan = RecruitmentPlan(
            name="Existing Candidate Free Plan",
            description="Pre-existing row",
            price=0,
            currency="VND",
            duration_days=30,
            max_job_posts=0,
            plan_audience=PlanAudience.CANDIDATE,
            is_free=True,
            is_active=is_active,
            is_deleted=is_deleted,
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan


def test_dry_run_reports_insert_without_writing(run_async):
    result = run_async(seed_candidate_free_plan(make_config(), apply=False))

    assert result.action == "would-insert"
    assert result.plan_id is None
    assert run_async(_load_all_plans()) == []


def test_apply_creates_plan_and_rerun_is_idempotent(run_async):
    result = run_async(seed_candidate_free_plan(make_config(), apply=True))

    assert result.action == "inserted"
    plans = run_async(_load_all_plans())
    assert len(plans) == 1
    plan = plans[0]
    assert plan.id == result.plan_id
    assert plan.name == "Test-only Candidate Free Plan"
    assert plan.plan_audience == PlanAudience.CANDIDATE
    assert plan.is_free is True
    assert plan.is_active is True
    assert plan.is_deleted is False

    rerun = run_async(seed_candidate_free_plan(make_config(), apply=True))

    assert rerun.action == "no-op"
    assert rerun.plan_id == plan.id
    assert len(run_async(_load_all_plans())) == 1


def test_missing_config_refuses_to_insert(run_async):
    with pytest.raises(SeedError, match="no --config"):
        run_async(seed_candidate_free_plan(None, apply=True))

    assert run_async(_load_all_plans()) == []


@pytest.mark.parametrize(
    ("is_active", "is_deleted", "reason"),
    [
        (False, False, "inactive"),
        (True, True, "soft-deleted"),
    ],
)
def test_existing_inactive_or_soft_deleted_plan_is_not_duplicated(
    run_async,
    is_active,
    is_deleted,
    reason,
):
    existing = run_async(_insert_plan(is_active=is_active, is_deleted=is_deleted))

    with pytest.raises(SeedError, match="inactive or soft-deleted"):
        run_async(seed_candidate_free_plan(make_config(), apply=True))

    plans = run_async(_load_all_plans())
    assert len(plans) == 1
    assert plans[0].id == existing.id
    assert plans[0].is_active is is_active
    assert plans[0].is_deleted is is_deleted


def test_invalid_config_is_rejected_before_database_access(tmp_path, run_async):
    config_path = tmp_path / "candidate_free_plan.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "Invalid",
                "description": "Invalid",
                "price": 0,
                "currency": "VND",
                "duration_days": 30,
                "max_job_posts": 0,
                "max_candidate_searches": 0,
                "max_ai_features": 0,
                "plan_audience": "company",
                "is_free": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SeedError, match="Invalid Candidate Free Plan"):
        load_config(config_path)

    assert run_async(_load_all_plans()) == []


def test_classify_detects_multiple_active_rows():
    rows = [
        SimpleNamespace(is_active=True, is_deleted=False),
        SimpleNamespace(is_active=True, is_deleted=False),
        SimpleNamespace(is_active=False, is_deleted=False),
    ]

    active, inactive = classify_candidate_free_plans(rows)

    assert len(active) == 2
    assert len(inactive) == 1


def test_classify_counts_soft_deleted_rows_as_inactive():
    rows = [
        SimpleNamespace(is_active=True, is_deleted=True),
        SimpleNamespace(is_active=False, is_deleted=False),
    ]

    active, inactive = classify_candidate_free_plans(rows)

    assert active == []
    assert len(inactive) == 2


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def _run_seeder_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_NAME"] = "ai_recruitment_platform_test"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "scripts.seed_candidate_free_plan", *args],
        cwd=str(_backend_dir()),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def test_cli_dry_run_exits_cleanly_without_unclosed_connection(tmp_path):
    config_path = tmp_path / "candidate_free_plan.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "Subprocess Candidate Free Plan",
                "description": "Subprocess-only fixture values; not a production plan.",
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

    completed = _run_seeder_cli("--config", str(config_path))

    assert completed.returncode == 0, completed.stderr
    assert "[DRY RUN]" in completed.stdout
    assert "Unclosed connection" not in completed.stderr


def test_cli_error_path_exits_cleanly_without_unclosed_connection():
    completed = _run_seeder_cli()

    assert completed.returncode == 1
    assert "[ERROR]" in completed.stdout
    assert "Unclosed connection" not in completed.stderr
