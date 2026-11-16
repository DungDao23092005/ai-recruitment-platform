"""Shared helpers and fixtures for company billing integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.database.session import async_session_factory
from app.domain.enums import (
    CompanySize,
    MembershipRole,
    MembershipStatus,
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    UserRole,
)
from app.domain.models.base import utc_now
from app.main import app
from app.models import (
    Company,
    CompanyMembership,
    RecruitmentPlan,
    Subscription,
    User,
)
from app.services.payment_providers.vnpay import VNPAYProvider
from tests.integration.conftest import _assert_not_development_database

PASSWORD = "password123"

settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"

CANONICAL_COMPANY_FREE_NAME = "Gói Doanh nghiệp Miễn phí"

_CANONICAL_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "company_free_plan.json"
)


def _load_canonical_plan_config() -> dict:
    """Load and strictly validate the canonical Company Free Plan configuration JSON.

    Treats backend/scripts/company_free_plan.json as the single source of truth.
    Raises clear exceptions on missing files, parse errors, or invalid/missing fields.
    No fallback defaults are substituted.
    """
    if not _CANONICAL_CONFIG_PATH.is_file():
        raise FileNotFoundError(
            f"Canonical Company Free Plan configuration file not found at: {_CANONICAL_CONFIG_PATH}"
        )

    try:
        raw_text = _CANONICAL_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse canonical Company Free Plan JSON at '{_CANONICAL_CONFIG_PATH}': {exc}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Failed to read canonical Company Free Plan configuration at '{_CANONICAL_CONFIG_PATH}': {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise TypeError(
            f"Canonical Company Free Plan configuration in '{_CANONICAL_CONFIG_PATH}' "
            f"must be a JSON object, got {type(data).__name__}"
        )

    required_fields = [
        "name",
        "description",
        "price",
        "currency",
        "duration_days",
        "max_job_posts",
        "max_candidate_searches",
        "max_ai_features",
        "plan_audience",
        "is_free",
        "display_order",
    ]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(
            f"Canonical Company Free Plan configuration is missing required fields: {missing}"
        )

    name = data["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            f"Invalid 'name' in canonical config: expected non-empty str, got {name!r}"
        )
    if name != CANONICAL_COMPANY_FREE_NAME:
        raise ValueError(
            f"Canonical name mismatch in '{_CANONICAL_CONFIG_PATH}': "
            f"expected {CANONICAL_COMPANY_FREE_NAME!r}, got {name!r}"
        )

    description = data["description"]
    if not isinstance(description, str) or not description.strip():
        raise ValueError(
            f"Invalid 'description' in canonical config: expected non-empty str, got {description!r}"
        )

    price = data["price"]
    if type(price) is not int or price != 0:
        raise ValueError(
            f"Invalid 'price' in canonical config: expected 0 (int), got {price!r}"
        )

    currency = data["currency"]
    if not isinstance(currency, str) or len(currency) < 3:
        raise ValueError(
            f"Invalid 'currency' in canonical config: expected str of at least 3 chars, got {currency!r}"
        )

    duration_days = data["duration_days"]
    if type(duration_days) is not int or duration_days <= 0:
        raise ValueError(
            f"Invalid 'duration_days' in canonical config: expected positive int, got {duration_days!r}"
        )

    max_job_posts = data["max_job_posts"]
    if type(max_job_posts) is not int or max_job_posts < 0:
        raise ValueError(
            f"Invalid 'max_job_posts' in canonical config: expected non-negative int, got {max_job_posts!r}"
        )

    max_candidate_searches = data["max_candidate_searches"]
    if type(max_candidate_searches) is not int or max_candidate_searches < 0:
        raise ValueError(
            f"Invalid 'max_candidate_searches' in canonical config: expected non-negative int, got {max_candidate_searches!r}"
        )

    max_ai_features = data["max_ai_features"]
    if type(max_ai_features) is not int or max_ai_features < 0:
        raise ValueError(
            f"Invalid 'max_ai_features' in canonical config: expected non-negative int, got {max_ai_features!r}"
        )

    audience_raw = data["plan_audience"]
    if isinstance(audience_raw, PlanAudience):
        audience = audience_raw
    elif isinstance(audience_raw, str) and audience_raw.strip().lower() == PlanAudience.COMPANY.value:
        audience = PlanAudience.COMPANY
    else:
        raise ValueError(
            f"Invalid 'plan_audience' in canonical config: expected '{PlanAudience.COMPANY.value}', got {audience_raw!r}"
        )

    is_free = data["is_free"]
    if is_free is not True:
        raise ValueError(
            f"Invalid 'is_free' in canonical config: expected True, got {is_free!r}"
        )

    display_order = data["display_order"]
    if type(display_order) is not int or display_order < 0:
        raise ValueError(
            f"Invalid 'display_order' in canonical config: expected non-negative int, got {display_order!r}"
        )

    return {
        "name": name,
        "description": description,
        "price": price,
        "currency": currency.upper(),
        "duration_days": duration_days,
        "max_job_posts": max_job_posts,
        "max_candidate_searches": max_candidate_searches,
        "max_ai_features": max_ai_features,
        "plan_audience": audience,
        "is_free": is_free,
        "display_order": display_order,
    }


def _validate_canonical_company_free_plan(
    plan: RecruitmentPlan, config: dict
) -> None:
    """Validate that an existing Company Free plan row matches the canonical specification.

    Raises RuntimeError if any field conflicts with canonical values.
    """
    conflicts: list[str] = []
    if plan.name != config["name"]:
        conflicts.append(f"name: expected {config['name']!r}, got {plan.name!r}")
    if plan.description != config["description"]:
        conflicts.append(
            f"description: expected {config['description']!r}, got {plan.description!r}"
        )
    if plan.price != config["price"]:
        conflicts.append(f"price: expected {config['price']!r}, got {plan.price!r}")
    if plan.currency != config["currency"]:
        conflicts.append(f"currency: expected {config['currency']!r}, got {plan.currency!r}")
    if plan.duration_days != config["duration_days"]:
        conflicts.append(f"duration_days: expected {config['duration_days']!r}, got {plan.duration_days!r}")
    if plan.max_job_posts != config["max_job_posts"]:
        conflicts.append(f"max_job_posts: expected {config['max_job_posts']!r}, got {plan.max_job_posts!r}")
    if (plan.max_candidate_searches or 0) != config["max_candidate_searches"]:
        conflicts.append(
            f"max_candidate_searches: expected {config['max_candidate_searches']!r}, got {plan.max_candidate_searches!r}"
        )
    if (plan.max_ai_features or 0) != config["max_ai_features"]:
        conflicts.append(
            f"max_ai_features: expected {config['max_ai_features']!r}, got {plan.max_ai_features!r}"
        )
    if plan.plan_audience != PlanAudience.COMPANY:
        conflicts.append(
            f"plan_audience: expected {PlanAudience.COMPANY!r}, got {plan.plan_audience!r}"
        )
    if plan.is_free is not True:
        conflicts.append(f"is_free: expected True, got {plan.is_free!r}")
    if (plan.display_order or 0) != config["display_order"]:
        conflicts.append(
            f"display_order: expected {config['display_order']!r}, got {plan.display_order!r}"
        )

    if conflicts:
        raise RuntimeError(
            f"Conflicting existing Company Free plan detected (id={plan.id}): "
            + "; ".join(conflicts)
            + ". Expected canonical Company Free configuration."
        )


async def _get_active_company_free_plan(session) -> RecruitmentPlan | None:
    """Retrieve the currently active Company Free plan from the test DB, if any."""
    return await session.scalar(
        select(RecruitmentPlan).where(
            RecruitmentPlan.plan_audience == PlanAudience.COMPANY,
            RecruitmentPlan.is_free == True,  # noqa: E712
            RecruitmentPlan.is_active == True,  # noqa: E712
            RecruitmentPlan.is_deleted == False,  # noqa: E712
        )
    )


async def _seed_canonical_company_free_plan() -> RecruitmentPlan:
    """Ensure an active canonical Company Free plan exists in the test DB.

    Validates that any existing active Company Free plan matches the approved
    specifications. Raises RuntimeError on conflicting limits.
    """
    _assert_not_development_database()
    config = _load_canonical_plan_config()

    async with async_session_factory() as session:
        existing = await _get_active_company_free_plan(session)
        if existing is not None:
            _validate_canonical_company_free_plan(existing, config)
            return existing

        plan = RecruitmentPlan(
            name=config["name"],
            description=config["description"],
            price=config["price"],
            currency=config["currency"],
            duration_days=config["duration_days"],
            max_job_posts=config["max_job_posts"],
            max_candidate_searches=config["max_candidate_searches"],
            max_ai_features=config["max_ai_features"],
            plan_audience=config["plan_audience"],
            is_free=True,
            is_active=True,
            is_deleted=False,
            display_order=config["display_order"],
        )
        session.add(plan)
        try:
            await session.commit()
            await session.refresh(plan)
            return plan
        except IntegrityError:
            await session.rollback()
            existing = await _get_active_company_free_plan(session)
            if existing is None:
                raise
            _validate_canonical_company_free_plan(existing, config)
            return existing


seed_canonical_company_free_plan = _seed_canonical_company_free_plan


def _load_company_billing_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "company_billing.py"
    )
    spec = importlib.util.spec_from_file_location(
        "company_billing", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _create_user(
    session,
    *,
    role: UserRole = UserRole.RECRUITER,
    email: str | None = None,
) -> User:
    user = User(
        email=email or f"u-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=get_password_hash(PASSWORD),
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_company(session, *, name: str | None = None) -> Company:
    suffix = uuid.uuid4().hex[:8]
    company = Company(
        name=name or f"Company {suffix}",
        slug=f"co-{suffix}",
        tax_code=f"TAX{suffix}".upper()[:18],
        size=CompanySize.SME,
    )
    session.add(company)
    await session.flush()
    return company


async def _create_membership(
    session,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MembershipRole = MembershipRole.ADMIN,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> CompanyMembership:
    membership = CompanyMembership(
        company_id=company_id,
        user_id=user_id,
        role=role,
        status=status,
    )
    session.add(membership)
    await session.flush()
    return membership


async def _create_plan(
    session,
    *,
    price: int = 500_000,
    audience: PlanAudience = PlanAudience.COMPANY,
    is_free: bool = False,
    max_job_posts: int = 10,
    max_candidate_searches: int = 20,
    max_ai_features: int = 15,
    duration_days: int = 30,
) -> RecruitmentPlan:
    plan = RecruitmentPlan(
        name=f"Plan {uuid.uuid4().hex[:8]}",
        price=price,
        currency="VND",
        duration_days=duration_days,
        max_job_posts=max_job_posts,
        max_candidate_searches=max_candidate_searches,
        max_ai_features=max_ai_features,
        plan_audience=audience,
        is_free=is_free,
        is_active=True,
        display_order=1,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _create_company_subscription(
    session,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    max_job_posts: int = 10,
    max_candidate_searches: int = 20,
    max_ai_features: int = 15,
    job_posts_used: int = 0,
    candidate_searches_used: int = 0,
    ai_features_used: int = 0,
    expires_at: datetime | None = ...,
) -> Subscription:
    now = utc_now()
    if expires_at is ...:
        expires_at = now + timedelta(days=30)
    sub = Subscription(
        user_id=user_id,
        company_id=company_id,
        plan_id=plan_id,
        scope=SubscriptionScope.COMPANY_RECRUITING,
        status=status,
        is_free=False,
        started_at=now if status == SubscriptionStatus.ACTIVE else None,
        expires_at=expires_at,
        max_job_posts=max_job_posts,
        max_candidate_searches=max_candidate_searches,
        max_ai_features=max_ai_features,
        job_posts_used=job_posts_used,
        candidate_searches_used=candidate_searches_used,
        ai_features_used=ai_features_used,
    )
    session.add(sub)
    await session.flush()
    return sub


async def _create_personal_subscription(
    session,
    *,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    scope: SubscriptionScope = SubscriptionScope.LEGACY_RECRUITER_PERSONAL,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    max_job_posts: int = 5,
    max_candidate_searches: int = 10,
    max_ai_features: int = 10,
) -> Subscription:
    now = utc_now()
    sub = Subscription(
        user_id=user_id,
        company_id=None,
        plan_id=plan_id,
        scope=scope,
        status=status,
        is_free=(scope == SubscriptionScope.CANDIDATE_PERSONAL and False),
        started_at=now,
        expires_at=now + timedelta(days=30),
        max_job_posts=max_job_posts,
        max_candidate_searches=max_candidate_searches,
        max_ai_features=max_ai_features,
        job_posts_used=0,
        candidate_searches_used=0,
        ai_features_used=0,
    )
    session.add(sub)
    await session.flush()
    return sub


async def _make_jwt_client_for_user(user: User) -> httpx.AsyncClient:
    token = create_access_token(user.id)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


def _build_signed_ipn(
    *,
    internal_order_id: str,
    amount_vnd: int,
    response_code: str = "00",
    transaction_status: str = "00",
) -> dict[str, str]:
    provider = VNPAYProvider()
    params = {
        "vnp_TmnCode": settings.VNPAY_TMN_CODE,
        "vnp_Amount": str(amount_vnd * 100),
        "vnp_BankCode": "NCB",
        "vnp_BankTranNo": f"BANK-{uuid.uuid4().hex[:8].upper()}",
        "vnp_CardType": "ATM",
        "vnp_PayDate": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "vnp_OrderInfo": f"Pay {internal_order_id}",
        "vnp_TransactionNo": f"TXN{uuid.uuid4().int % 10**10}",
        "vnp_ResponseCode": response_code,
        "vnp_TransactionStatus": transaction_status,
        "vnp_TxnRef": internal_order_id,
    }
    params["vnp_SecureHash"] = provider.generate_secure_hash(params)
    return params
