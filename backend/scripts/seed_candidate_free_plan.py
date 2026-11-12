#!/usr/bin/env python
"""Provision the Candidate Free Plan from explicit operator configuration.

This script never invents plan values. It is a dry run unless ``--apply`` is
provided, and it refuses to modify or duplicate existing Candidate Free Plan
rows. See ``candidate_free_plan.example.json`` for the required configuration
shape.

Usage:
    python -m scripts.seed_candidate_free_plan --config candidate_free_plan.json
    python -m scripts.seed_candidate_free_plan --config candidate_free_plan.json --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError as PydanticValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.session import async_session_factory, engine
from app.domain.enums import PlanAudience
from app.models import RecruitmentPlan

logger = logging.getLogger(__name__)


class SeedError(RuntimeError):
    """Raised when the Candidate Free Plan cannot be provisioned safely."""


class CandidateFreePlanConfig(BaseModel):
    """Every business value must be supplied explicitly by the operator."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=5000)
    price: int = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=10)
    duration_days: int = Field(..., gt=0)
    max_job_posts: int = Field(..., ge=0)
    max_candidate_searches: int | None = Field(..., ge=0)
    max_ai_features: int | None = Field(..., ge=0)
    plan_audience: PlanAudience
    is_free: bool
    display_order: int = Field(default=0, ge=0)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_candidate_free(self) -> "CandidateFreePlanConfig":
        if self.plan_audience != PlanAudience.CANDIDATE:
            raise ValueError("plan_audience must be 'candidate'")
        if self.is_free is not True:
            raise ValueError("is_free must be true")
        return self


@dataclass(frozen=True)
class SeedResult:
    action: Literal["no-op", "would-insert", "inserted"]
    plan_id: uuid.UUID | None
    message: str


def load_config(path: Path) -> CandidateFreePlanConfig:
    """Load and validate an explicit Candidate Free Plan configuration."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SeedError(f"Cannot read config file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SeedError(f"Config file is not valid JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise SeedError("Config root must be a JSON object")

    try:
        return CandidateFreePlanConfig.model_validate(payload)
    except PydanticValidationError as exc:
        raise SeedError(f"Invalid Candidate Free Plan configuration:\n{exc}") from exc


def classify_candidate_free_plans(
    plans: Sequence[RecruitmentPlan],
) -> tuple[list[RecruitmentPlan], list[RecruitmentPlan]]:
    """Split rows into usable active plans and inactive/soft-deleted rows."""
    active = [plan for plan in plans if plan.is_active and not plan.is_deleted]
    inactive = [plan for plan in plans if not (plan.is_active and not plan.is_deleted)]
    return active, inactive


async def _load_candidate_free_plans() -> list[RecruitmentPlan]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(RecruitmentPlan)
            .where(
                RecruitmentPlan.plan_audience == PlanAudience.CANDIDATE,
                RecruitmentPlan.is_free == True,  # noqa: E712
            )
            .order_by(RecruitmentPlan.id)
        )
        return list(result.scalars().all())


async def seed_candidate_free_plan(
    config: CandidateFreePlanConfig | None,
    *,
    apply: bool,
) -> SeedResult:
    """Create the Candidate Free Plan exactly once, or report why not.

    ``apply=False`` never writes to the database. An existing active plan is
    left untouched. Inactive or soft-deleted rows are never reactivated or
    duplicated automatically.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(RecruitmentPlan)
            .where(
                RecruitmentPlan.plan_audience == PlanAudience.CANDIDATE,
                RecruitmentPlan.is_free == True,  # noqa: E712
            )
            .order_by(RecruitmentPlan.id)
        )
        plans = list(result.scalars().all())
        active, inactive = classify_candidate_free_plans(plans)

        if len(active) > 1:
            ids = ", ".join(str(plan.id) for plan in active)
            raise SeedError(
                "Multiple active Candidate Free Plans found "
                f"({ids}). Resolve the duplicate rows manually."
            )

        if active:
            plan = active[0]
            return SeedResult(
                action="no-op",
                plan_id=plan.id,
                message=(
                    "[OK] An active Candidate Free Plan already exists "
                    f"({plan.id}). No changes made."
                ),
            )

        if inactive:
            ids = ", ".join(str(plan.id) for plan in inactive)
            raise SeedError(
                "Candidate Free Plan row(s) already exist but are inactive or "
                f"soft-deleted ({ids}). Refusing to create a duplicate. "
                "Resolve the existing row manually."
            )

        if config is None:
            raise SeedError(
                "No active Candidate Free Plan exists and no --config was "
                "supplied. Provide explicit plan values before seeding."
            )

        plan = RecruitmentPlan(
            name=config.name,
            description=config.description,
            price=config.price,
            currency=config.currency,
            duration_days=config.duration_days,
            max_job_posts=config.max_job_posts,
            max_candidate_searches=config.max_candidate_searches,
            max_ai_features=config.max_ai_features,
            plan_audience=config.plan_audience,
            is_free=config.is_free,
            is_active=True,
            display_order=config.display_order,
        )

        if not apply:
            return SeedResult(
                action="would-insert",
                plan_id=None,
                message=(
                    f"[DRY RUN] Would create Candidate Free Plan "
                    f"'{config.name}'. Re-run with --apply to write."
                ),
            )

        session.add(plan)
        try:
            await session.commit()
            await session.refresh(plan)
        except IntegrityError as exc:
            await session.rollback()
            plans = await _load_candidate_free_plans()
            active, _ = classify_candidate_free_plans(plans)
            if len(active) == 1:
                existing = active[0]
                return SeedResult(
                    action="no-op",
                    plan_id=existing.id,
                    message=(
                        "[OK] An active Candidate Free Plan already exists "
                        f"({existing.id}). No changes made."
                    ),
                )
            raise SeedError(
                "Candidate Free Plan insert conflicted with an existing row. "
                "Resolve the catalog manually."
            ) from exc
        except Exception:
            await session.rollback()
            raise

        return SeedResult(
            action="inserted",
            plan_id=plan.id,
            message=(
                f"[OK] Created Candidate Free Plan '{plan.name}' ({plan.id})."
            ),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision the Candidate Free Plan from explicit configuration.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to a JSON file containing every required plan value.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the plan. Without this flag the script only performs a dry run.",
    )
    return parser


async def _run_cli(
    config: CandidateFreePlanConfig | None,
    *,
    apply: bool,
) -> SeedResult:
    """Run the seeder and release pooled connections before the loop closes."""
    original_error: BaseException | None = None
    try:
        return await seed_candidate_free_plan(config, apply=apply)
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        try:
            await engine.dispose()
        except Exception:
            if original_error is None:
                raise
            logger.warning(
                "Failed to dispose the database engine cleanly.",
                exc_info=True,
            )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config) if args.config else None
        result = asyncio.run(_run_cli(config, apply=args.apply))
    except (SeedError, OSError) as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1) from exc

    print(result.message)


if __name__ == "__main__":
    main()
