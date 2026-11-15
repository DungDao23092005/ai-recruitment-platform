"""SQL Server integrity coverage for workspace memberships and invitations."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictException
from app.database.base_class import utc_now
from app.database.session import async_session_factory
from app.domain.enums import (
    CompanySize,
    InvitationStatus,
    MembershipRole,
    MembershipStatus,
    PlanAudience,
    SubscriptionScope,
    SubscriptionStatus,
    UserRole,
)
from app.models import (
    Company,
    CompanyInvitation,
    CompanyMembership,
    RecruitmentPlan,
    Subscription,
    User,
)
from app.repositories.company_membership_repository import (
    CompanyMembershipRepository,
)
from app.services.workspace_service import (
    WorkspaceContext,
    WorkspaceService,
    hash_invitation_token,
)

pytestmark = pytest.mark.integration


def _company(slug: str) -> Company:
    return Company(
        name=f"Company {slug}",
        slug=slug,
        tax_code=f"TAX-{slug}"[:50],
        size=CompanySize.STARTUP,
    )


def _user(role: UserRole = UserRole.RECRUITER) -> User:
    return User(
        email=f"user-{uuid.uuid4()}@example.com",
        password_hash="hash",
        role=role,
        is_active=True,
    )


def _membership(
    company: Company,
    user: User,
    *,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    is_deleted: bool = False,
) -> CompanyMembership:
    return CompanyMembership(
        company_id=company.id,
        user_id=user.id,
        role=MembershipRole.RECRUITER,
        status=status,
        is_deleted=is_deleted,
    )


def _invitation(
    company: Company,
    inviter: User,
    *,
    email: str | None = None,
    status: InvitationStatus = InvitationStatus.PENDING,
    is_deleted: bool = False,
) -> CompanyInvitation:
    return CompanyInvitation(
        company_id=company.id,
        email=email or f"invite-{uuid.uuid4()}@example.com",
        role=MembershipRole.RECRUITER,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        status=status,
        invited_by_id=inviter.id,
        expires_at=utc_now() + timedelta(days=7),
        is_deleted=is_deleted,
    )


async def _ensure_company_plan(session) -> RecruitmentPlan:
    result = await session.execute(
        select(RecruitmentPlan).where(
            RecruitmentPlan.plan_audience == PlanAudience.COMPANY,
            RecruitmentPlan.is_active == True,
            RecruitmentPlan.is_deleted == False,
        )
    )
    plan = result.scalars().first()
    if plan is None:
        plan = RecruitmentPlan(
            name=f"Company Free {uuid.uuid4().hex[:6]}",
            price=0,
            currency="VND",
            duration_days=30,
            max_job_posts=1,
            max_candidate_searches=10,
            max_ai_features=5,
            plan_audience=PlanAudience.COMPANY,
            is_free=True,
            is_active=True,
            display_order=1,
        )
        session.add(plan)
        await session.flush()
    return plan


async def _create_company_subscription(
    session,
    company: Company,
    owner: User | None = None,
) -> Subscription:
    plan = await _ensure_company_plan(session)
    now = utc_now()
    if owner is None:
        owner = _user()
        session.add(owner)
        await session.flush()
    sub = Subscription(
        user_id=owner.id,
        company_id=company.id,
        plan_id=plan.id,
        scope=SubscriptionScope.COMPANY_RECRUITING,
        status=SubscriptionStatus.ACTIVE,
        is_free=plan.is_free,
        started_at=now,
        expires_at=None,
        max_job_posts=plan.max_job_posts,
        max_candidate_searches=plan.max_candidate_searches,
        max_ai_features=plan.max_ai_features,
        job_posts_used=0,
        candidate_searches_used=0,
        ai_features_used=0,
    )
    session.add(sub)
    await session.flush()
    return sub


class TestMembershipFilteredUniqueIndex:
    def test_duplicate_active_membership_rejected(self, session, run_async):
        async def _test() -> None:
            company = _company(f"dupe-{uuid.uuid4().hex[:8]}")
            user = _user()
            session.add_all([company, user])
            await session.flush()

            session.add(_membership(company, user))
            await session.flush()
            session.add(_membership(company, user))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        run_async(_test())

    def test_revoked_or_soft_deleted_rows_do_not_block_active(
        self, session, run_async
    ):
        async def _test() -> None:
            company = _company(f"reuse-{uuid.uuid4().hex[:8]}")
            user = _user()
            session.add_all([company, user])
            await session.flush()

            session.add(
                _membership(
                    company, user, status=MembershipStatus.REVOKED
                )
            )
            session.add(
                _membership(
                    company, user,
                    status=MembershipStatus.ACTIVE,
                    is_deleted=True,
                )
            )
            await session.flush()

            active = _membership(company, user)
            session.add(active)
            await session.flush()
            assert active.id is not None

        run_async(_test())


class TestInvitationFilteredUniqueIndex:
    def test_duplicate_pending_invitation_rejected(self, session, run_async):
        async def _test() -> None:
            company = _company(f"invite-{uuid.uuid4().hex[:8]}")
            inviter = _user()
            email = f"candidate-{uuid.uuid4()}@example.com"
            session.add_all([company, inviter])
            await session.flush()

            session.add(_invitation(company, inviter, email=email))
            await session.flush()
            session.add(_invitation(company, inviter, email=email))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        run_async(_test())

    def test_revoked_pending_invitation_allows_reinvite(
        self, session, run_async
    ):
        async def _test() -> None:
            company = _company(f"reinvite-{uuid.uuid4().hex[:8]}")
            inviter = _user()
            email = f"candidate-{uuid.uuid4()}@example.com"
            session.add_all([company, inviter])
            await session.flush()

            session.add(
                _invitation(
                    company,
                    inviter,
                    email=email,
                    status=InvitationStatus.REVOKED,
                )
            )
            await session.flush()
            session.add(_invitation(company, inviter, email=email))
            await session.flush()

        run_async(_test())


class TestMembershipTenantIsolation:
    def test_membership_does_not_grant_other_company_access(
        self, session, run_async
    ):
        async def _test() -> None:
            company_a = _company(f"tenant-a-{uuid.uuid4().hex[:8]}")
            company_b = _company(f"tenant-b-{uuid.uuid4().hex[:8]}")
            user = _user()
            other_user = _user()
            session.add_all([company_a, company_b, user, other_user])
            await session.flush()
            session.add(_membership(company_a, user))
            session.add(_membership(company_b, other_user))
            await session.flush()

            repo = CompanyMembershipRepository(session, CompanyMembership)
            assert await repo.get_active(user.id, company_a.id) is not None
            assert await repo.get_active(user.id, company_b.id) is None
            active = await repo.list_active_for_user(user.id)
            assert [m.company_id for m in active] == [company_a.id]

        run_async(_test())


class TestLastAdminProtection:
    def test_last_admin_cannot_be_revoked(self, session, run_async):
        async def _test() -> None:
            company = _company(f"last-admin-{uuid.uuid4().hex[:8]}")
            admin = _user()
            session.add_all([company, admin])
            await session.flush()
            membership = _membership(company, admin)
            membership.role = MembershipRole.ADMIN
            session.add(membership)
            await session.flush()

            service = WorkspaceService(session)
            context = WorkspaceContext(
                user=admin,
                company=company,
                membership=membership,
            )
            with pytest.raises(
                ConflictException, match="last active workspace admin"
            ):
                await service.revoke_membership(context, membership.id)
            await session.rollback()

        run_async(_test())

    def test_concurrent_admins_cannot_revoke_each_other(self, run_async):
        async def _test() -> None:
            company = _company(f"admin-race-{uuid.uuid4().hex[:8]}")
            admin_a = _user()
            admin_b = _user()
            async with async_session_factory() as setup:
                setup.add_all([company, admin_a, admin_b])
                await setup.flush()
                membership_a = _membership(company, admin_a)
                membership_b = _membership(company, admin_b)
                membership_a.role = MembershipRole.ADMIN
                membership_b.role = MembershipRole.ADMIN
                setup.add_all([membership_a, membership_b])
                await setup.commit()
                company_id = company.id
                a_id, b_id = admin_a.id, admin_b.id
                ma_id, mb_id = membership_a.id, membership_b.id

            barrier = asyncio.Barrier(2)

            async def revoke_as(
                actor_id: uuid.UUID,
                actor_membership_id: uuid.UUID,
                target_membership_id: uuid.UUID,
            ) -> str:
                async with async_session_factory() as session:
                    actor = await session.get(User, actor_id)
                    company_row = await session.get(Company, company_id)
                    actor_membership = await session.get(
                        CompanyMembership, actor_membership_id
                    )
                    assert actor is not None
                    assert company_row is not None
                    assert actor_membership is not None
                    context = WorkspaceContext(
                        user=actor,
                        company=company_row,
                        membership=actor_membership,
                    )
                    service = WorkspaceService(session)
                    await barrier.wait()
                    try:
                        await service.revoke_membership(
                            context, target_membership_id
                        )
                    except ConflictException:
                        return "conflict"
                    return "success"

            outcomes = await asyncio.gather(
                revoke_as(a_id, ma_id, mb_id),
                revoke_as(b_id, mb_id, ma_id),
            )

            assert sorted(outcomes) == ["conflict", "success"]

            async with async_session_factory() as verify:
                admins = await CompanyMembershipRepository(
                    verify, CompanyMembership
                ).count_active_admins(company_id)
                assert admins == 1

        run_async(_test())


class TestLastAdminDemotionConcurrency:
    def test_concurrent_admins_cannot_demote_each_other(self, run_async):
        async def _test() -> None:
            company = _company(f"demote-race-{uuid.uuid4().hex[:8]}")
            admin_a = _user()
            admin_b = _user()
            async with async_session_factory() as setup:
                setup.add_all([company, admin_a, admin_b])
                await setup.flush()
                membership_a = _membership(company, admin_a)
                membership_b = _membership(company, admin_b)
                membership_a.role = MembershipRole.ADMIN
                membership_b.role = MembershipRole.ADMIN
                setup.add_all([membership_a, membership_b])
                await setup.commit()
                company_id = company.id
                a_id, b_id = admin_a.id, admin_b.id
                ma_id, mb_id = membership_a.id, membership_b.id

            barrier = asyncio.Barrier(2)

            async def demote_as(
                actor_id: uuid.UUID,
                actor_membership_id: uuid.UUID,
                target_membership_id: uuid.UUID,
            ) -> str:
                async with async_session_factory() as session:
                    actor = await session.get(User, actor_id)
                    company_row = await session.get(Company, company_id)
                    actor_membership = await session.get(
                        CompanyMembership, actor_membership_id
                    )
                    assert actor is not None
                    assert company_row is not None
                    assert actor_membership is not None
                    context = WorkspaceContext(
                        user=actor,
                        company=company_row,
                        membership=actor_membership,
                    )
                    service = WorkspaceService(session)
                    await barrier.wait()
                    try:
                        await service.update_membership_role(
                            context,
                            target_membership_id,
                            MembershipRole.RECRUITER,
                        )
                    except ConflictException:
                        return "conflict"
                    return "success"

            outcomes = await asyncio.gather(
                demote_as(a_id, ma_id, mb_id),
                demote_as(b_id, mb_id, ma_id),
            )

            assert sorted(outcomes) == ["conflict", "success"]

            async with async_session_factory() as verify:
                admins = await CompanyMembershipRepository(
                    verify, CompanyMembership
                ).count_active_admins(company_id)
                assert admins == 1

        run_async(_test())


class TestInvitationAcceptance:
    def test_accept_marks_invitation_and_creates_membership(
        self, session, run_async
    ):
        async def _test() -> None:
            company = _company(f"accept-{uuid.uuid4().hex[:8]}")
            inviter = _user()
            invitee = _user()
            invitee.email = f"invitee-{uuid.uuid4()}@example.com"
            session.add_all([company, inviter, invitee])
            await session.flush()

            token = secrets_token()
            invitation = _invitation(
                company, inviter, email=invitee.email
            )
            invitation.token_hash = hash_invitation_token(token)
            session.add(invitation)
            await session.flush()

            service = WorkspaceService(session)
            result = await service.accept_invitation(invitee, token)
            assert result.workspace.company_id == company.id
            assert result.workspace.role == MembershipRole.RECRUITER

            await session.refresh(invitation)
            assert invitation.status == InvitationStatus.ACCEPTED
            active = await CompanyMembershipRepository(
                session, CompanyMembership
            ).get_active(invitee.id, company.id)
            assert active is not None

        run_async(_test())

    def test_accept_invitation_activates_membership(
        self, session, run_async
    ):
        """Gap B — Accepting an invitation activates membership and preserves existing company subscription."""
        async def _test() -> None:
            company = _company(f"accept-sub-{uuid.uuid4().hex[:8]}")
            inviter = _user()
            invitee = _user()
            invitee.email = f"invitee-{uuid.uuid4()}@example.com"
            session.add_all([company, inviter, invitee])
            await session.flush()

            # Arrange: Create exactly one active company subscription using _create_company_subscription(session, company)
            existing_sub = await _create_company_subscription(session, company, inviter)
            existing_sub_id = existing_sub.id

            token = secrets_token()
            invitation = _invitation(
                company, inviter, email=invitee.email
            )
            invitation.token_hash = hash_invitation_token(token)
            session.add(invitation)
            await session.flush()

            service = WorkspaceService(session)
            result = await service.accept_invitation(invitee, token)

            # 1. Invitee membership is ACTIVE and belongs to the correct company.
            assert result.workspace.company_id == company.id
            assert result.workspace.role == MembershipRole.RECRUITER
            active_membership = await CompanyMembershipRepository(
                session, CompanyMembership
            ).get_active(invitee.id, company.id)
            assert active_membership is not None
            assert active_membership.status == MembershipStatus.ACTIVE
            assert active_membership.company_id == company.id
            assert active_membership.user_id == invitee.id

            # 2. The company has exactly one ACTIVE subscription with:
            # - scope = company_recruiting
            # - company_id = the invited workspace's company ID.
            stmt = select(Subscription).where(
                Subscription.company_id == company.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.is_deleted == False,
            )
            active_company_subs = (await session.execute(stmt)).scalars().all()
            assert len(active_company_subs) == 1
            company_sub = active_company_subs[0]
            assert company_sub.scope == SubscriptionScope.COMPANY_RECRUITING
            assert company_sub.company_id == company.id

            # 3. No company_recruiting subscription is created with user_id belonging to the invitee.
            stmt_invitee = select(Subscription).where(
                Subscription.user_id == invitee.id,
                Subscription.scope == SubscriptionScope.COMPANY_RECRUITING,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.is_deleted == False,
            )
            invitee_subs = (await session.execute(stmt_invitee)).scalars().all()
            assert len(invitee_subs) == 0

            # 4. Existing company subscription ID remains unchanged.
            assert company_sub.id == existing_sub_id

            # 5. The company's quota entitlement remains bound to company_id and is shared by membership.
            assert company_sub.company_id == company.id
            assert company_sub.max_job_posts == existing_sub.max_job_posts
            assert company_sub.max_candidate_searches == existing_sub.max_candidate_searches
            assert company_sub.max_ai_features == existing_sub.max_ai_features

        run_async(_test())


def secrets_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)
