"""Shared helpers and fixtures for Wave 1.4 Phase 2 company billing integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import uuid

import httpx
from sqlalchemy import select

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
from tests.integration.api.conftest import PASSWORD

settings.VNPAY_TMN_CODE = "TESTTMN"
settings.VNPAY_HASH_SECRET = "testhashsecret123"


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
