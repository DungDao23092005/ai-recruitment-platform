"""Integration coverage for one-active-evaluation-per-interview-per-evaluator.

Two layers are proven here:

* the ORM metadata declares the filtered unique index (so ``create_all`` and the
  migration agree), and
* the SQL Server database actually rejects a second *active* scorecard for the
  same interview/evaluator while still allowing a fresh one once the previous is
  soft-deleted.

The Alembic revision ``add_interview_eval_uniqueness`` is executed through
an operations context so the shipped DDL is what gets validated.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.database.session import async_session_factory
from app.domain.enums import (
    ApplicationStatus,
    CompanySize,
    InterviewStatus,
    InterviewType,
    JobStatus,
    JobType,
    UserRole,
    WorkplaceType,
)
from app.models import (
    Application,
    CandidateProfile,
    Company,
    Interview,
    InterviewEvaluation,
    Job,
    RecruiterProfile,
    User,
)

pytestmark = pytest.mark.integration

_INDEX_NAME = "uq_interview_evaluations_interview_evaluator_active"
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "add_interview_evaluation_uniqueness.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "add_interview_eval_uniqueness", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_upgrade(connection, migration):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        migration.upgrade()


def _apply_downgrade(connection, migration):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        migration.downgrade()


def _drop_index(connection) -> None:
    connection.exec_driver_sql(
        f"IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = '{_INDEX_NAME}' "
        "AND object_id = OBJECT_ID('interview_evaluations')) "
        f"DROP INDEX {_INDEX_NAME} ON interview_evaluations"
    )


def _index_meta(connection):
    result = connection.execute(
        sa.text(
            """
            SELECT i.is_unique, i.has_filter, i.filter_definition
            FROM sys.indexes i
            WHERE i.name = :name
              AND i.object_id = OBJECT_ID('interview_evaluations')
            """
        ),
        {"name": _INDEX_NAME},
    )
    return result.first()


async def _seed_interview(session):
    company = Company(
        id=uuid.uuid4(),
        name="Uniqueness Co",
        slug=f"uniqueness-co-{uuid.uuid4().hex[:8]}",
        tax_code=str(uuid.uuid4().int)[:12],
        size=CompanySize.STARTUP,
    )
    session.add(company)
    await session.flush()

    candidate_user = User(
        id=uuid.uuid4(),
        email=f"cand-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
        is_active=True,
    )
    evaluator_a = User(
        id=uuid.uuid4(),
        email=f"rec-a-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )
    evaluator_b = User(
        id=uuid.uuid4(),
        email=f"rec-b-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )
    session.add_all([candidate_user, evaluator_a, evaluator_b])
    await session.flush()

    session.add(RecruiterProfile(user_id=evaluator_a.id, company_id=company.id))
    session.add(RecruiterProfile(user_id=evaluator_b.id, company_id=company.id))

    candidate_profile = CandidateProfile(
        id=uuid.uuid4(),
        user_id=candidate_user.id,
        full_name="Uniqueness Candidate",
    )
    session.add(candidate_profile)
    await session.flush()

    job = Job(
        id=uuid.uuid4(),
        company_id=company.id,
        title="Uniqueness Job",
        description="desc",
        status=JobStatus.PUBLISHED,
        job_type=JobType.FULL_TIME,
        workplace_type=WorkplaceType.REMOTE,
        location="Remote",
    )
    session.add(job)
    await session.flush()

    application = Application(
        id=uuid.uuid4(),
        candidate_id=candidate_profile.id,
        job_id=job.id,
        status=ApplicationStatus.INTERVIEWING,
    )
    session.add(application)
    await session.flush()

    interview = Interview(
        id=uuid.uuid4(),
        application_id=application.id,
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        interview_type=InterviewType.TECHNICAL,
        status=InterviewStatus.SCHEDULED,
    )
    session.add(interview)
    await session.flush()

    return application, interview, evaluator_a.id, evaluator_b.id


class TestFilteredUniqueIndexMetadata:
    def test_orm_declares_filtered_unique_index(self):
        indexes = {index.name: index for index in InterviewEvaluation.__table__.indexes}
        index = indexes.get(_INDEX_NAME)
        assert index is not None
        assert index.unique is True
        # A filtered index is only meaningful with the predicate attached.
        assert index.dialect_options["mssql"]["where"] is not None


class TestEvaluationUniquenessMigration:
    def test_upgrade_creates_filtered_unique_index(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_drop_index)
                await conn.run_sync(_apply_upgrade, migration)
                await session.commit()
                conn = await session.connection()
                meta = await conn.run_sync(_index_meta)

            assert meta is not None
            assert meta[0] is True  # is_unique
            assert meta[1] is True  # has_filter
            assert "is_deleted" in (meta[2] or "")

        run_async(_test())

    def test_downgrade_drops_index(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_drop_index)
                await conn.run_sync(_apply_upgrade, migration)
                await session.commit()
                conn = await session.connection()
                assert await conn.run_sync(_index_meta) is not None

                await conn.run_sync(_apply_downgrade, migration)
                await session.commit()
                conn = await session.connection()
                assert await conn.run_sync(_index_meta) is None

            # Restore for the remaining tests in this module/session.
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_apply_upgrade, migration)
                await session.commit()

        run_async(_test())


class TestEvaluationUniquenessBehaviour:
    def test_duplicate_active_scorecard_is_rejected(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                _, interview, evaluator_a, _ = await _seed_interview(session)
                await session.commit()
                interview_id, evaluator_a_id = interview.id, evaluator_a

            async with async_session_factory() as session:
                session.add(
                    InterviewEvaluation(
                        interview_id=interview_id,
                        application_id=(
                            await session.get(Interview, interview_id)
                        ).application_id,
                        evaluator_id=evaluator_a_id,
                        rating=5,
                    )
                )
                await session.commit()

            async with async_session_factory() as session:
                session.add(
                    InterviewEvaluation(
                        interview_id=interview_id,
                        application_id=(
                            await session.get(Interview, interview_id)
                        ).application_id,
                        evaluator_id=evaluator_a_id,
                        rating=3,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()

        run_async(_test())

    def test_distinct_evaluators_may_each_score(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                _, interview, evaluator_a, evaluator_b = await _seed_interview(
                    session
                )
                await session.commit()
                interview_id = interview.id
                application_id = interview.application_id

            async with async_session_factory() as session:
                session.add_all(
                    [
                        InterviewEvaluation(
                            interview_id=interview_id,
                            application_id=application_id,
                            evaluator_id=evaluator_a,
                            rating=4,
                        ),
                        InterviewEvaluation(
                            interview_id=interview_id,
                            application_id=application_id,
                            evaluator_id=evaluator_b,
                            rating=2,
                        ),
                    ]
                )
                await session.commit()

        run_async(_test())

    def test_soft_delete_frees_the_slot(self, run_async):
        async def _test():
            async with async_session_factory() as session:
                _, interview, evaluator_a, _ = await _seed_interview(session)
                await session.commit()
                interview_id = interview.id
                application_id = interview.application_id

            async with async_session_factory() as session:
                session.add(
                    InterviewEvaluation(
                        interview_id=interview_id,
                        application_id=application_id,
                        evaluator_id=evaluator_a,
                        rating=5,
                    )
                )
                await session.commit()

            async with async_session_factory() as session:
                first = (
                    await session.execute(
                        sa.select(InterviewEvaluation).where(
                            InterviewEvaluation.interview_id == interview_id,
                            InterviewEvaluation.evaluator_id == evaluator_a,
                            InterviewEvaluation.is_deleted == sa.false(),
                        )
                    )
                ).scalar_one()
                first.is_deleted = True
                await session.commit()

            async with async_session_factory() as session:
                session.add(
                    InterviewEvaluation(
                        interview_id=interview_id,
                        application_id=application_id,
                        evaluator_id=evaluator_a,
                        rating=1,
                    )
                )
                await session.commit()

        run_async(_test())
