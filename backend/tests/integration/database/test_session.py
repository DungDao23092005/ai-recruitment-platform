from sqlalchemy import text

from app.database.session import async_session_factory, engine
from app.domain.enums import UserRole
from app.models import User


def test_database_connection_works(run_async):
    async def _check():
        async with engine.connect() as conn:
            return (await conn.execute(text("SELECT 1"))).scalar()

    assert run_async(_check()) == 1


def test_connection_uses_test_database(run_async):
    async def _check():
        async with engine.connect() as conn:
            return (await conn.execute(text("SELECT DB_NAME()"))).scalar()

    assert run_async(_check()) == "ai_recruitment_platform_test"


def test_session_commit_persists_row(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = User(
                email="commit@example.com",
                password_hash="hashed",
                role=UserRole.CANDIDATE,
            )
            session.add(user)
            await session.commit()
            user_id = user.id
        async with async_session_factory() as session:
            return await session.get(User, user_id)

    fetched = run_async(_run())
    assert fetched is not None
    assert fetched.email == "commit@example.com"


def test_session_rollback_discards_changes(run_async):
    async def _run():
        async with async_session_factory() as session:
            user = User(
                email="rollback@example.com",
                password_hash="hashed",
                role=UserRole.CANDIDATE,
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            await session.rollback()
        async with async_session_factory() as session:
            return await session.get(User, user_id)

    assert run_async(_run()) is None
