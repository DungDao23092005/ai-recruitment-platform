"""Regression tests for SQL Server compilation of resume boolean predicates.

SQL Server has no boolean literal type, so SQLAlchemy's ``.is_(False)`` renders
``IS 0`` (and ``.is_(True)`` renders ``IS 1``), both of which SQL Server rejects
with a syntax error. The repository must use dialect-safe equality predicates
instead. These tests compile the real repository statements with the MSSQL
dialect and fail if ``IS 0``/``IS 1`` reappears.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import mssql

from app.models import Resume
from app.repositories import ResumeRepository


def _resume(**overrides) -> Resume:
    data = {
        "id": uuid.uuid4(),
        "candidate_id": uuid.uuid4(),
        "title": "cv.pdf",
        "is_primary": False,
        "is_confirmed": False,
        "parsed_data": {"full_name": "Jane Doe", "skills": ["Python"]},
    }
    data.update(overrides)
    return Resume(**data)


def _capture_session(resume: Resume | None = None) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = resume
    result.scalars.return_value.first.return_value = resume
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _compile_mssql(statement) -> str:
    return str(
        statement.compile(
            dialect=mssql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _assert_no_boolean_is_literals(sql: str) -> None:
    normalized = " ".join(sql.upper().split())
    assert " IS 0" not in normalized
    assert " IS 1" not in normalized


def test_primary_lookup_compiles_for_sql_server():
    session = _capture_session()
    repository = ResumeRepository(session, Resume)

    asyncio.run(repository.get_primary_by_candidate(uuid.uuid4()))

    sql = _compile_mssql(session.execute.await_args_list[-1].args[0])
    _assert_no_boolean_is_literals(sql)
    normalized = " ".join(sql.lower().split())
    assert "resumes.is_primary = 1" in normalized
    assert "resumes.is_confirmed = 1" in normalized
    assert "resumes.is_deleted = 0" in normalized


def test_latest_draft_lookup_compiles_for_sql_server():
    session = _capture_session()
    repository = ResumeRepository(session, Resume)

    asyncio.run(repository.get_latest_draft_by_candidate(uuid.uuid4()))

    sql = _compile_mssql(session.execute.await_args_list[-1].args[0])
    _assert_no_boolean_is_literals(sql)
    normalized = " ".join(sql.lower().split())
    assert "resumes.is_confirmed = 0" in normalized
    assert "resumes.is_deleted = 0" in normalized


def test_owned_lookup_compiles_for_sql_server():
    session = _capture_session()
    repository = ResumeRepository(session, Resume)

    asyncio.run(repository.get_owned_by_id(uuid.uuid4(), uuid.uuid4()))

    sql = _compile_mssql(session.execute.await_args_list[-1].args[0])
    _assert_no_boolean_is_literals(sql)
    assert "resumes.is_deleted = 0" in " ".join(sql.lower().split())


def test_confirmation_updates_compile_for_sql_server():
    resume = _resume()
    session = _capture_session(resume=resume)
    repository = ResumeRepository(session, Resume)

    asyncio.run(
        repository.confirm_draft(
            resume_id=resume.id,
            candidate_id=resume.candidate_id,
            parsed_data={"full_name": "Jane Doe", "skills": ["Python"]},
        )
    )

    update_statements = [
        call.args[0] for call in session.execute.await_args_list
    ]
    assert len(update_statements) == 3
    for statement in update_statements:
        _assert_no_boolean_is_literals(_compile_mssql(statement))
