import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.enums import CompanySize, JobType, UserRole, WorkplaceType
from app.models import Company, Job, User


def make_user(email="repo@example.com", role=UserRole.CANDIDATE) -> User:
    return User(email=email, password_hash="hashed", role=role)


def test_create_persists_and_assigns_id(session, make_repo, run_async):
    async def _run():
        created = await make_repo(User).create(make_user())
        await session.commit()
        return created

    created = run_async(_run())
    assert created.id is not None
    assert created.email == "repo@example.com"


def test_get_by_id_returns_matching_row(session, make_repo, run_async):
    async def _run():
        repo = make_repo(User)
        created = await repo.create(make_user())
        await session.commit()
        return await repo.get_by_id(created.id)

    fetched = run_async(_run())
    assert fetched is not None
    assert fetched.id is not None
    assert fetched.email == "repo@example.com"


def test_get_by_id_returns_none_for_missing(session, make_repo, run_async):
    assert run_async(make_repo(User).get_by_id(uuid.uuid4())) is None


def test_list_all_returns_all_active(session, make_repo, run_async):
    async def _run():
        repo = make_repo(User)
        await repo.create(make_user("a@example.com"))
        await repo.create(make_user("b@example.com"))
        await session.commit()
        return await repo.list_all()

    users = run_async(_run())
    assert len(users) == 2


def test_update_persists_changes(session, make_repo, run_async):
    async def _run():
        repo = make_repo(User)
        created = await repo.create(make_user())
        created.email = "updated@example.com"
        await repo.update(created)
        await session.commit()
        return await repo.get_by_id(created.id)

    fetched = run_async(_run())
    assert fetched is not None
    assert fetched.email == "updated@example.com"


def test_soft_delete_hides_row(session, make_repo, run_async):
    async def _run():
        repo = make_repo(User)
        created = await repo.create(make_user())
        await repo.soft_delete(created)
        await session.commit()
        return await repo.get_by_id(created.id), await repo.list_all()

    fetched, remaining = run_async(_run())
    assert fetched is None
    assert remaining == []


def test_fk_constraint_rejects_unknown_company(session, make_repo, run_async):
    async def _run():
        repo = make_repo(Job)
        job = Job(
            company_id=uuid.uuid4(),
            title="Job",
            description="desc",
            job_type=JobType.FULL_TIME,
            workplace_type=WorkplaceType.REMOTE,
        )
        with pytest.raises(IntegrityError):
            await repo.create(job)
        await session.rollback()

    run_async(_run())


def test_unique_constraint_blocks_duplicate_active_slug(session, make_repo, run_async):
    async def _run():
        repo = make_repo(Company)
        await repo.create(
            Company(name="Acme", slug="acme", tax_code="111", size=CompanySize.STARTUP)
        )
        await session.commit()
        with pytest.raises(IntegrityError):
            await repo.create(
                Company(name="Acme 2", slug="acme", tax_code="222", size=CompanySize.SME)
            )
        await session.rollback()

    run_async(_run())


def test_filtered_unique_index_allows_slug_reuse_after_soft_delete(
    session, make_repo, run_async
):
    async def _run():
        repo = make_repo(Company)
        first = await repo.create(
            Company(name="Acme", slug="reuse", tax_code="111", size=CompanySize.STARTUP)
        )
        await session.commit()
        await repo.soft_delete(first)
        await session.commit()
        second = await repo.create(
            Company(name="Acme 2", slug="reuse", tax_code="222", size=CompanySize.SME)
        )
        await session.commit()
        return second

    second = run_async(_run())
    assert second.id is not None
    assert second.slug == "reuse"
