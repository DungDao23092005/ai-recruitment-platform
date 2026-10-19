"""Integration coverage for the hiring-pipeline Alembic revision.

The disposable SQL Server test database is reset from ORM metadata, so the new
objects are dropped first and then re-created by actually running the revision's
``upgrade()`` through an Alembic operations context. This proves the revision
applies cleanly and produces the expected NVARCHAR/constraint schema, and that
the guarded ``downgrade()`` refuses to destroy data.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import pytest
import sqlalchemy as sa

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
    ApplicationActivity,
    ApplicationNote,
    CandidateProfile,
    Company,
    Interview,
    InterviewEvaluation,
    Job,
    User,
)

pytestmark = pytest.mark.integration

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "add_hiring_pipeline_tables.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "add_hiring_pipeline_tables", _MIGRATION_PATH
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


def _drop_pipeline_objects(connection) -> None:
    """Remove the ORM-created objects so the revision can create them again."""
    InterviewEvaluation.__table__.drop(connection, checkfirst=True)
    ApplicationActivity.__table__.drop(connection, checkfirst=True)
    ApplicationNote.__table__.drop(connection, checkfirst=True)
    connection.exec_driver_sql(
        "IF OBJECT_ID('uq_interviews_id_application_id', 'UQ') IS NOT NULL "
        "ALTER TABLE interviews DROP CONSTRAINT uq_interviews_id_application_id"
    )


def _column_info(connection, table_name):
    result = connection.execute(
        sa.text(
            """
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {row[0]: (row[1].lower(), row[2]) for row in result}


def _constraint_types(connection, table_name):
    result = connection.execute(
        sa.text(
            """
            SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
            WHERE TABLE_NAME = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {row[0]: row[1] for row in result}


def _index_names(connection, table_name):
    result = connection.execute(
        sa.text(
            """
            SELECT i.name
            FROM sys.indexes i
            WHERE i.object_id = OBJECT_ID(:table_name)
            """
        ),
        {"table_name": table_name},
    )
    return {row[0] for row in result}


async def _seed_application(session):
    company = Company(
        id=uuid.uuid4(),
        name="Migration Co",
        slug=f"migration-co-{uuid.uuid4()}",
        tax_code=str(uuid.uuid4().int)[:12],
        size=CompanySize.STARTUP,
    )
    session.add(company)
    await session.flush()

    candidate_user = User(
        id=uuid.uuid4(),
        email=f"cand-{uuid.uuid4()}@test.com",
        password_hash="hash",
        role=UserRole.CANDIDATE,
        is_active=True,
    )
    recruiter_user = User(
        id=uuid.uuid4(),
        email=f"rec-{uuid.uuid4()}@test.com",
        password_hash="hash",
        role=UserRole.RECRUITER,
        is_active=True,
    )
    session.add_all([candidate_user, recruiter_user])
    await session.flush()

    candidate_profile = CandidateProfile(
        id=uuid.uuid4(),
        user_id=candidate_user.id,
        full_name="Migration Candidate",
    )
    session.add(candidate_profile)
    await session.flush()

    job = Job(
        id=uuid.uuid4(),
        company_id=company.id,
        title="Migration Job",
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
        status=ApplicationStatus.APPLIED,
    )
    session.add(application)
    await session.flush()

    return application, recruiter_user


class TestHiringPipelineUpgradeSchema:
    def test_upgrade_creates_tables_with_nvarchar_columns(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_drop_pipeline_objects)
                await conn.run_sync(_apply_upgrade, migration)
                await session.commit()
                conn = await session.connection()

                notes = await conn.run_sync(_column_info, "application_notes")
                assert notes["content"][0] == "nvarchar"
                assert notes["content"][1] == 2000

                evaluations = await conn.run_sync(
                    _column_info, "interview_evaluations"
                )
                assert evaluations["recommendation"] == ("nvarchar", 20)
                assert evaluations["strengths"] == ("nvarchar", 1000)
                assert evaluations["weaknesses"] == ("nvarchar", 1000)
                assert evaluations["notes"] == ("nvarchar", 2000)

                activities = await conn.run_sync(
                    _column_info, "application_activities"
                )
                assert activities["action_type"] == ("nvarchar", 50)
                assert activities["from_status"] == ("nvarchar", 50)
                assert activities["to_status"] == ("nvarchar", 50)
                assert activities["note"] == ("nvarchar", 1000)
                assert activities["metadata_json"][0] == "nvarchar"

        run_async(_test())

    def test_upgrade_creates_constraints_and_indexes(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_drop_pipeline_objects)
                await conn.run_sync(_apply_upgrade, migration)
                await session.commit()
                conn = await session.connection()

                interview_constraints = await conn.run_sync(
                    _constraint_types, "interviews"
                )
                assert (
                    interview_constraints["uq_interviews_id_application_id"]
                    == "UNIQUE"
                )

                evaluation_constraints = await conn.run_sync(
                    _constraint_types, "interview_evaluations"
                )
                assert (
                    evaluation_constraints[
                        "fk_interview_evaluations_interview_application"
                    ]
                    == "FOREIGN KEY"
                )
                assert (
                    evaluation_constraints[
                        "ck_interview_evaluations_rating_range"
                    ]
                    == "CHECK"
                )
                assert (
                    evaluation_constraints[
                        "ck_interview_evaluations_recommendation"
                    ]
                    == "CHECK"
                )

                assert "ix_application_notes_application_id" in (
                    await conn.run_sync(_index_names, "application_notes")
                )
                assert "ix_application_activities_application_id" in (
                    await conn.run_sync(_index_names, "application_activities")
                )
                evaluation_indexes = await conn.run_sync(
                    _index_names, "interview_evaluations"
                )
                assert "ix_interview_evaluations_interview_id" in evaluation_indexes
                assert (
                    "ix_interview_evaluations_application_id" in evaluation_indexes
                )

        run_async(_test())

    def test_downgrade_drops_empty_tables(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(_drop_pipeline_objects)
                await conn.run_sync(_apply_upgrade, migration)
                await session.commit()
                conn = await session.connection()

                await conn.run_sync(_apply_downgrade, migration)
                await session.commit()
                conn = await session.connection()

                remaining = await conn.run_sync(
                    _constraint_types, "interviews"
                )
                assert (
                    "uq_interviews_id_application_id" not in remaining
                )

        run_async(_test())


class TestHiringPipelineDowngradeGuard:
    def test_allows_downgrade_when_tables_are_empty(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                conn = await session.connection()
                await conn.run_sync(migration._assert_downgrade_safe)

        run_async(_test())

    def test_refuses_downgrade_with_application_note(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                application, author = await _seed_application(session)
                session.add(
                    ApplicationNote(
                        application_id=application.id,
                        author_id=author.id,
                        content="internal note",
                    )
                )
                await session.commit()

                conn = await session.connection()
                with pytest.raises(
                    RuntimeError, match="Refusing to drop hiring pipeline tables"
                ):
                    await conn.run_sync(migration._assert_downgrade_safe)

        run_async(_test())

    def test_refuses_downgrade_with_interview_evaluation(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                application, evaluator = await _seed_application(session)
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
                session.add(
                    InterviewEvaluation(
                        interview_id=interview.id,
                        application_id=application.id,
                        evaluator_id=evaluator.id,
                        rating=5,
                        recommendation="strong_hire",
                    )
                )
                await session.commit()

                conn = await session.connection()
                with pytest.raises(
                    RuntimeError, match="Refusing to drop hiring pipeline tables"
                ):
                    await conn.run_sync(migration._assert_downgrade_safe)

        run_async(_test())

    def test_refuses_downgrade_with_activity(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                application, actor = await _seed_application(session)
                session.add(
                    ApplicationActivity(
                        application_id=application.id,
                        actor_id=actor.id,
                        action_type="status_changed",
                        from_status="applied",
                        to_status="under_review",
                    )
                )
                await session.commit()

                conn = await session.connection()
                with pytest.raises(
                    RuntimeError, match="Refusing to drop hiring pipeline tables"
                ):
                    await conn.run_sync(migration._assert_downgrade_safe)

        run_async(_test())

    def test_guard_reports_rows_for_each_table(self, run_async):
        async def _test():
            migration = _load_migration()
            async with async_session_factory() as session:
                application, actor = await _seed_application(session)
                session.add(
                    ApplicationNote(
                        application_id=application.id,
                        author_id=actor.id,
                        content="note",
                    )
                )
                session.add(
                    ApplicationActivity(
                        application_id=application.id,
                        actor_id=actor.id,
                        action_type="status_changed",
                    )
                )
                await session.commit()

                conn = await session.connection()
                rows = await conn.run_sync(migration._remaining_row_counts)
                tables = {row[0] for row in rows}
                assert tables == {
                    "application_notes",
                    "application_activities",
                }

        run_async(_test())
