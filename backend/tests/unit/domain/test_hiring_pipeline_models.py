"""Unit tests for the hiring-pipeline ORM models (schema/metadata only).

These tests inspect the declarative metadata that both ``create_all`` (used by
the disposable integration database) and the Alembic migration are built from.
SQL Server Unicode mappings are asserted through the MSSQL dialect so the
NVARCHAR contract is covered without a live database.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import mssql

from app.models import (
    ApplicationActivity,
    ApplicationNote,
    Interview,
    InterviewEvaluation,
)


def _mssql_ddl(column) -> str:
    """Compile a column's type as SQL Server would render it (e.g. NVARCHAR)."""
    return column.type.compile(dialect=mssql.dialect())


def _column_names(model) -> set[str]:
    return {col.name for col in model.__table__.columns}


def _index_names(model) -> set[str]:
    return {idx.name for idx in model.__table__.indexes}


def _check_constraint_names(model) -> set[str]:
    return {
        c.name
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint)
    }


class TestApplicationNoteModel:
    def test_table_name(self):
        assert ApplicationNote.__tablename__ == "application_notes"

    def test_columns(self):
        assert _column_names(ApplicationNote) == {
            "id",
            "application_id",
            "author_id",
            "content",
            "created_at",
            "updated_at",
            "is_deleted",
        }

    def test_foreign_keys(self):
        fks = {fk.parent.name: tuple(fk.target_fullname.split(".")) for fk in ApplicationNote.__table__.foreign_keys}
        assert fks["application_id"] == ("applications", "id")
        assert fks["author_id"] == ("users", "id")

    def test_content_is_required_and_bounded_unicode(self):
        content = ApplicationNote.__table__.c.content
        assert content.nullable is False
        assert _mssql_ddl(content) == "NVARCHAR(2000)"

    def test_application_id_indexed(self):
        assert "ix_application_notes_application_id" in _index_names(ApplicationNote)

    def test_soft_delete_present(self):
        assert ApplicationNote.__table__.c.is_deleted.nullable is False


class TestInterviewEvaluationModel:
    def test_table_name(self):
        assert InterviewEvaluation.__tablename__ == "interview_evaluations"

    def test_columns(self):
        assert _column_names(InterviewEvaluation) == {
            "id",
            "interview_id",
            "application_id",
            "evaluator_id",
            "rating",
            "strengths",
            "weaknesses",
            "recommendation",
            "notes",
            "created_at",
            "updated_at",
            "is_deleted",
        }

    def test_rating_is_required(self):
        assert InterviewEvaluation.__table__.c.rating.nullable is False

    def test_bounded_unicode_columns(self):
        expected_lengths = {
            "strengths": 1000,
            "weaknesses": 1000,
            "recommendation": 20,
            "notes": 2000,
        }
        for name, length in expected_lengths.items():
            col = InterviewEvaluation.__table__.c[name]
            assert col.nullable is True
            assert _mssql_ddl(col) == f"NVARCHAR({length})"

    def test_evaluator_foreign_key(self):
        fks = {
            fk.parent.name: tuple(fk.target_fullname.split("."))
            for fk in InterviewEvaluation.__table__.foreign_keys
        }
        assert fks["evaluator_id"] == ("users", "id")
        assert fks["application_id"] == ("applications", "id")

    def test_composite_foreign_key_prevents_mismatched_pair(self):
        composite = [
            c
            for c in InterviewEvaluation.__table__.constraints
            if isinstance(c, ForeignKeyConstraint) and len(c.columns) == 2
        ]
        assert len(composite) == 1
        constraint = composite[0]
        assert constraint.name == "fk_interview_evaluations_interview_application"
        assert {col.name for col in constraint.columns} == {
            "interview_id",
            "application_id",
        }
        assert constraint.elements[0].target_fullname.startswith("interviews.")
        targets = {e.target_fullname for e in constraint.elements}
        assert targets == {"interviews.id", "interviews.application_id"}

    def test_check_constraints(self):
        assert _check_constraint_names(InterviewEvaluation) == {
            "ck_interview_evaluations_rating_range",
            "ck_interview_evaluations_recommendation",
        }

    def test_indexes(self):
        assert {
            "ix_interview_evaluations_interview_id",
            "ix_interview_evaluations_application_id",
        } <= _index_names(InterviewEvaluation)


class TestApplicationActivityModel:
    def test_table_name(self):
        assert ApplicationActivity.__tablename__ == "application_activities"

    def test_is_append_only(self):
        cols = _column_names(ApplicationActivity)
        assert "created_at" in cols
        # Append-only: no mutation or soft-delete bookkeeping columns.
        assert "updated_at" not in cols
        assert "is_deleted" not in cols

    def test_columns(self):
        assert _column_names(ApplicationActivity) == {
            "id",
            "application_id",
            "actor_id",
            "action_type",
            "from_status",
            "to_status",
            "note",
            "metadata_json",
            "created_at",
        }

    def test_foreign_keys(self):
        fks = {
            fk.parent.name: tuple(fk.target_fullname.split("."))
            for fk in ApplicationActivity.__table__.foreign_keys
        }
        assert fks["application_id"] == ("applications", "id")
        assert fks["actor_id"] == ("users", "id")

    def test_action_type_bounded_unicode(self):
        col = ApplicationActivity.__table__.c.action_type
        assert col.nullable is False
        assert _mssql_ddl(col) == "NVARCHAR(50)"

    def test_optional_columns(self):
        for name, length in {
            "from_status": 50,
            "to_status": 50,
            "note": 1000,
        }.items():
            col = ApplicationActivity.__table__.c[name]
            assert col.nullable is True
            assert _mssql_ddl(col) == f"NVARCHAR({length})"

    def test_metadata_json_is_unbounded_unicode(self):
        col = ApplicationActivity.__table__.c.metadata_json
        assert col.nullable is True
        assert _mssql_ddl(col) == "NVARCHAR(max)"

    def test_application_id_indexed(self):
        assert "ix_application_activities_application_id" in _index_names(
            ApplicationActivity
        )


class TestInterviewUniqueTarget:
    def test_interviews_has_composite_unique_constraint(self):
        unique = {
            c.name: tuple(col.name for col in c.columns)
            for c in Interview.__table__.constraints
            if isinstance(c, UniqueConstraint)
        }
        assert unique.get("uq_interviews_id_application_id") == (
            "id",
            "application_id",
        )
