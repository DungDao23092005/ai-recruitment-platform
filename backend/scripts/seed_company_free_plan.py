#!/usr/bin/env python
"""Provision the canonical Company Free Plan from explicit configuration.

This script never invents plan values. It is a dry run unless ``--apply`` is
provided, and it refuses to modify or duplicate existing Company Free Plan
rows. An existing active plan is left untouched so Admin-edited quotas are
preserved across reruns. See ``company_free_plan.json`` for the canonical
configuration shipped with the repository.

Usage:
    python -m scripts.seed_company_free_plan --config company_free_plan.json
    python -m scripts.seed_company_free_plan --config company_free_plan.json --apply
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
    """Raised when the Company Free Plan cannot be provisioned safely."""


class CompanyFreePlanConfig(BaseModel):
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
    def validate_company_free(self) -> "CompanyFreePlanConfig":
        if self.plan_audience != PlanAudience.COMPANY:
            raise ValueError("plan_audience must be 'company'")
        if self.is_free is not True:
            raise ValueError("is_free must be true")
        if self.price != 0:
            raise ValueError("price must be 0 for the Company Free plan")
        return self


@dataclass(frozen=True)
class SeedResult:
    action: Literal["no-op", "would-insert", "inserted"]
    plan_id: uuid.UUID | None
    message: str


def load_config(path: Path) -> CompanyFreePlanConfig:
    """Load and validate an explicit Company Free Plan configuration."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SeedError(f"Cannot read config file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SeedError(f"Config file is not valid JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise SeedError("Config root must be a JSON object")

    try:
        return CompanyFreePlanConfig.model_validate(payload)
    except PydanticValidationError as exc:
        raise SeedError(f"Invalid Company Free Plan configuration:\n{exc}") from exc


def classify_company_free_plans(
    plans: Sequence[RecruitmentPlan],
) -> tuple[list[RecruitmentPlan], list[RecruitmentPlan]]:
    """Split rows into usable active plans and inactive/soft-deleted rows."""
    active = [plan for plan in plans if plan.is_active and not plan.is_deleted]
    inactive = [plan for plan in plans if not (plan.is_active and not plan.is_deleted)]
    return active, inactive


async def _load_company_free_plans() -> list[RecruitmentPlan]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(RecruitmentPlan)
            .where(
                RecruitmentPlan.plan_audience == PlanAudience.COMPANY,
                RecruitmentPlan.is_free == True,  # noqa: E712
            )
            .order_by(RecruitmentPlan.id)
        )
        return list(result.scalars().all())


async def seed_company_free_plan(
    config: CompanyFreePlanConfig | None,
    *,
    apply: bool,
) -> SeedResult:
    """Create the Company Free Plan exactly once, or report why not.

    ``apply=False`` never writes to the database. An existing active plan is
    left untouched, which preserves any Admin-edited quotas. Inactive or
    soft-deleted rows are never reactivated or duplicated automatically.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(RecruitmentPlan)
            .where(
                RecruitmentPlan.plan_audience == PlanAudience.COMPANY,
                RecruitmentPlan.is_free == True,  # noqa: E712
            )
            .order_by(RecruitmentPlan.id)
        )
        plans = list(result.scalars().all())
        active, inactive = classify_company_free_plans(plans)

        if len(active) > 1:
            ids = ", ".join(str(plan.id) for plan in active)
            raise SeedError(
                "Multiple active Company Free Plans found "
                f"({ids}). Resolve the duplicate rows manually."
            )

        if active:
            plan = active[0]
            return SeedResult(
                action="no-op",
                plan_id=plan.id,
                message=(
                    "[OK] An active Company Free Plan already exists "
                    f"({plan.id}). No changes made."
                ),
            )

        if inactive:
            ids = ", ".join(str(plan.id) for plan in inactive)
            raise SeedError(
                "Company Free Plan row(s) already exist but are inactive or "
                f"soft-deleted ({ids}). Refusing to create a duplicate. "
                "Resolve the existing row manually."
            )

        if config is None:
            raise SeedError(
                "No active Company Free Plan exists and no --config was "
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
                    f"[DRY RUN] Would create Company Free Plan "
                    f"'{config.name}'. Re-run with --apply to write."
                ),
            )

        session.add(plan)
        try:
            await session.commit()
            await session.refresh(plan)
        except IntegrityError as exc:
            await session.rollback()
            plans = await _load_company_free_plans()
            active, _ = classify_company_free_plans(plans)
            if len(active) == 1:
                existing = active[0]
                return SeedResult(
                    action="no-op",
                    plan_id=existing.id,
                    message=(
                        "[OK] An active Company Free Plan already exists "
                        f"({existing.id}). No changes made."
                    ),
                )
            raise SeedError(
                "Company Free Plan insert conflicted with an existing row. "
                "Resolve the catalog manually."
            ) from exc
        except Exception:
            await session.rollback()
            raise

        return SeedResult(
            action="inserted",
            plan_id=plan.id,
            message=(
                f"[OK] Created Company Free Plan '{plan.name}' ({plan.id})."
            ),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision the Company Free Plan from explicit configuration.",
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
    config: CompanyFreePlanConfig | None,
    *,
    apply: bool,
) -> SeedResult:
    """Run the seeder and release pooled connections before the loop closes."""
    original_error: BaseException | None = None
    try:
        return await seed_company_free_plan(config, apply=apply)
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
