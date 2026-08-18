import uuid
from datetime import datetime, timezone

from app.domain.enums import (
    ApplicationStatus,
    CompanySize,
    JobStatus,
    JobType,
    UserRole,
    WorkplaceType,
)
from app.models import Application, CandidateProfile, Company, Job, Skill, User
from app.repositories.application_repository import ApplicationRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.user_repository import UserRepository


def make_user(email="candidate@example.com", role=UserRole.CANDIDATE) -> User:
    return User(email=email, password_hash="hashed", role=role)


def make_company(slug="acme", tax_code="111") -> Company:
    return Company(name="Acme", slug=slug, tax_code=tax_code, size=CompanySize.STARTUP)


def make_job(company_id, status=JobStatus.PUBLISHED, title="Job") -> Job:
    return Job(
        company_id=company_id,
        title=title,
        description="desc",
        status=status,
        job_type=JobType.FULL_TIME,
        workplace_type=WorkplaceType.REMOTE,
    )


def test_user_repository_get_by_email(session, run_async):
    async def _run():
        repo = UserRepository(session, User)
        created = await repo.create(make_user("u@example.com"))
        await session.commit()
        return created, await repo.get_by_email("u@example.com")

    created, found = run_async(_run())
    assert found is not None
    assert found.id == created.id
    assert found.email == "u@example.com"


def test_user_repository_get_by_email_missing(session, run_async):
    repo = UserRepository(session, User)
    assert run_async(repo.get_by_email("nobody@example.com")) is None


def test_user_repository_get_with_profile(session, run_async):
    async def _run():
        repo = UserRepository(session, User)
        user = make_user("u2@example.com")
        user.candidate_profile = CandidateProfile(full_name="John")
        await repo.create(user)
        await session.commit()
        return await repo.get_with_profile(user.id)

    found = run_async(_run())
    assert found is not None
    assert found.candidate_profile is not None
    assert found.candidate_profile.full_name == "John"


def test_company_repository_get_by_slug(session, run_async):
    async def _run():
        repo = CompanyRepository(session, Company)
        created = await repo.create(make_company(slug="acme", tax_code="111"))
        await session.commit()
        return created, await repo.get_by_slug("acme")

    created, found = run_async(_run())
    assert found is not None
    assert found.id == created.id
    assert found.slug == "acme"


def test_company_repository_get_by_slug_missing(session, run_async):
    repo = CompanyRepository(session, Company)
    assert run_async(repo.get_by_slug("missing")) is None


def test_company_repository_get_by_tax_code(session, run_async):
    async def _run():
        repo = CompanyRepository(session, Company)
        created = await repo.create(make_company(slug="acme2", tax_code="222"))
        await session.commit()
        return created, await repo.get_by_tax_code("222")

    created, found = run_async(_run())
    assert found is not None
    assert found.id == created.id
    assert found.tax_code == "222"


def test_job_repository_list_active_jobs_filters_status(session, run_async):
    async def _run():
        company = CompanyRepository(session, Company)
        created_company = await company.create(make_company(slug="co1", tax_code="t1"))
        repo = JobRepository(session, Job)
        await repo.create(make_job(created_company.id, status=JobStatus.PUBLISHED, title="A"))
        await repo.create(make_job(created_company.id, status=JobStatus.DRAFT, title="B"))
        await repo.create(make_job(created_company.id, status=JobStatus.CLOSED, title="C"))
        await session.commit()
        return await repo.list_active_jobs(skip=0, limit=10)

    jobs = run_async(_run())
    assert [job.title for job in jobs] == ["A"]


def test_job_repository_list_active_jobs_skip_limit(session, run_async):
    async def _run():
        company = CompanyRepository(session, Company)
        created_company = await company.create(make_company(slug="co2", tax_code="t2"))
        repo = JobRepository(session, Job)
        await repo.create(make_job(created_company.id, title="A"))
        await repo.create(make_job(created_company.id, title="B"))
        await repo.create(make_job(created_company.id, status=JobStatus.DRAFT, title="C"))
        await session.commit()
        return await repo.list_active_jobs(skip=0, limit=1), await repo.list_active_jobs(
            skip=1, limit=10
        )

    one, rest = run_async(_run())
    assert len(one) == 1
    assert len(rest) == 1


def test_job_repository_get_job_with_skills(session, run_async):
    async def _run():
        company = CompanyRepository(session, Company)
        created_company = await company.create(make_company(slug="co3", tax_code="t3"))
        repo = JobRepository(session, Job)
        job = make_job(created_company.id, title="Python Job")
        job.skills.append(Skill(name="Python"))
        await repo.create(job)
        await session.commit()
        return await repo.get_job_with_skills(job.id)

    found = run_async(_run())
    assert found is not None
    assert len(found.skills) == 1
    assert found.skills[0].name == "Python"


def test_application_repository_get_by_candidate_and_job(session, run_async):
    async def _run():
        user = UserRepository(session, User)
        created_user = await user.create(make_user("app@example.com"))
        candidate = CandidateProfile(user_id=created_user.id, full_name="Cand")
        session.add(candidate)
        await session.flush()
        company = CompanyRepository(session, Company)
        created_company = await company.create(make_company(slug="co4", tax_code="t4"))
        job_repo = JobRepository(session, Job)
        created_job = await job_repo.create(make_job(created_company.id, title="J"))
        application = Application(candidate_id=candidate.id, job_id=created_job.id)
        session.add(application)
        await session.commit()
        repo = ApplicationRepository(session, Application)
        return (
            await repo.get_by_candidate_and_job(candidate.id, created_job.id),
            await repo.get_by_candidate_and_job(candidate.id, uuid.uuid4()),
            await repo.list_by_candidate(candidate.id),
            await repo.list_by_job(created_job.id),
        )

    found, missing, by_candidate, by_job = run_async(_run())
    assert found is not None
    assert found.status == ApplicationStatus.APPLIED
    assert missing is None
    assert len(by_candidate) == 1
    assert len(by_job) == 1


def test_application_repository_list_by_candidate_paginated(session, run_async):
    def make_app(candidate_id, job_id, created_at):
        return Application(
            candidate_id=candidate_id,
            job_id=job_id,
            created_at=created_at,
        )

    async def _run():
        user = UserRepository(session, User)
        created_user = await user.create(make_user("pag@example.com"))
        candidate = CandidateProfile(user_id=created_user.id, full_name="Cand")
        session.add(candidate)
        await session.flush()
        company = CompanyRepository(session, Company)
        created_company = await company.create(
            make_company(slug="co5", tax_code="t5")
        )
        job_repo = JobRepository(session, Job)
        job_a = await job_repo.create(make_job(created_company.id, title="A"))
        job_b = await job_repo.create(make_job(created_company.id, title="B"))
        job_c = await job_repo.create(make_job(created_company.id, title="C"))
        repo = ApplicationRepository(session, Application)
        session.add_all(
            [
                make_app(
                    candidate.id,
                    job_a.id,
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
                make_app(
                    candidate.id,
                    job_b.id,
                    datetime(2026, 1, 2, tzinfo=timezone.utc),
                ),
                make_app(
                    candidate.id,
                    job_c.id,
                    datetime(2026, 1, 3, tzinfo=timezone.utc),
                ),
            ]
        )
        await session.commit()
        first_page = await repo.list_by_candidate_paginated(
            candidate.id, skip=0, limit=2
        )
        second_page = await repo.list_by_candidate_paginated(
            candidate.id, skip=2, limit=2
        )
        return first_page, second_page

    first_page, second_page = run_async(_run())
    assert [app.job.title for app in first_page] == ["C", "B"]
    assert [app.job.title for app in second_page] == ["A"]
    assert first_page[0].job.company.name == "Acme"
