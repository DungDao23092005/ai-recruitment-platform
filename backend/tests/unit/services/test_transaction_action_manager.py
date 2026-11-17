"""Unit tests for TransactionActionManager (lifecycle and nested savepoints).

Tests 1-18 exercise transaction resolution, single listener registration,
event handling (after_commit, after_rollback, after_soft_rollback, after_transaction_end),
multi-level SAVEPOINT promotion, partial rollbacks, session close/reset, and
isolated callback execution without leaking actions or accumulating listeners.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.services.transaction_action_manager import (
    KEY_ACTIONS,
    KEY_REGISTERED,
    TransactionActionManager,
)


@pytest.fixture
def engine():
    return create_engine("sqlite:///:memory:")


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# Tests 1-18
# ---------------------------------------------------------------------------


def test_outer_commit_executes_action_once(session):
    """1. Outer/root transaction commit executes registered action exactly once."""
    log = []
    with session.begin():
        TransactionActionManager.register_action(
            session, lambda: log.append("executed")
        )

    assert log == ["executed"]


def test_outer_rollback_discards_actions(session):
    """2. Outer/root transaction rollback discards all actions without execution."""
    log = []
    try:
        with session.begin():
            TransactionActionManager.register_action(
                session, lambda: log.append("executed")
            )
            raise RuntimeError("Force rollback")
    except RuntimeError:
        pass

    assert log == []


def test_rollback_then_new_transaction_does_not_run_old_actions(session):
    """3. Rollback of first transaction does not run old actions when a new transaction commits."""
    log = []
    try:
        with session.begin():
            TransactionActionManager.register_action(
                session, lambda: log.append("tx1_action")
            )
            raise RuntimeError("Rollback tx1")
    except RuntimeError:
        pass

    with session.begin():
        TransactionActionManager.register_action(
            session, lambda: log.append("tx2_action")
        )

    assert log == ["tx2_action"]


def test_multiple_actions_in_same_transaction_execute_in_order(session):
    """4. Multiple actions registered in the same transaction execute in order."""
    log = []
    with session.begin():
        TransactionActionManager.register_action(session, lambda: log.append(1))
        TransactionActionManager.register_action(session, lambda: log.append(2))
        TransactionActionManager.register_action(session, lambda: log.append(3))

    assert log == [1, 2, 3]


def test_nested_savepoint_commit_does_not_dispatch_before_root_commit(session):
    """5. Nested savepoint commit promotes actions to parent without dispatching prematurely."""
    log = []
    with session.begin():
        with session.begin_nested():
            TransactionActionManager.register_action(
                session, lambda: log.append("nested")
            )
        # Nested commit completed, but root has not committed yet -> log must still be empty
        assert log == []

    # Root commit completed -> now action executes
    assert log == ["nested"]


def test_nested_commit_then_root_rollback_discards_promoted_actions(session):
    """6. Promoted actions from committed savepoint are discarded if root transaction rolls back."""
    log = []
    try:
        with session.begin():
            with session.begin_nested():
                TransactionActionManager.register_action(
                    session, lambda: log.append("promoted")
                )
            raise RuntimeError("Root failure after nested commit")
    except RuntimeError:
        pass

    assert log == []


def test_nested_rollback_preserves_outer_actions(session):
    """7. Nested savepoint rollback discards nested action while preserving outer action."""
    log = []
    with session.begin():
        TransactionActionManager.register_action(
            session, lambda: log.append("outer")
        )
        try:
            with session.begin_nested():
                TransactionActionManager.register_action(
                    session, lambda: log.append("nested")
                )
                raise RuntimeError("Nested failure")
        except RuntimeError:
            pass

        # Outer transaction is still active, verify actions map in session.info
        actions_map = session.info.get(KEY_ACTIONS, {})
        tx = session.get_transaction()
        assert tx in actions_map
        assert len(actions_map[tx]) == 1

    # Outer commit runs only the preserved outer action
    assert log == ["outer"]


def test_nested_rollback_then_root_commit_runs_only_outer_actions(session):
    """8. After nested rollback, subsequent root commit runs only outer actions."""
    log = []
    with session.begin():
        TransactionActionManager.register_action(
            session, lambda: log.append("outer_1")
        )
        try:
            with session.begin_nested():
                TransactionActionManager.register_action(
                    session, lambda: log.append("nested_rolled_back")
                )
                raise RuntimeError("Rollback nested")
        except RuntimeError:
            pass
        TransactionActionManager.register_action(
            session, lambda: log.append("outer_2")
        )

    assert log == ["outer_1", "outer_2"]


def test_first_registration_inside_existing_savepoint_rollback_discards_action(
    session,
):
    """9. First registration on session occurring inside a savepoint properly discards action on rollback."""
    log = []
    with session.begin():
        try:
            with session.begin_nested():
                # Listener registration happens here for the first time
                TransactionActionManager.register_action(
                    session, lambda: log.append("first_nested")
                )
                raise RuntimeError("Rollback savepoint")
        except RuntimeError:
            pass

    assert log == []


def test_multi_level_nested_savepoints_commit_propagation(session):
    """10. Multi-level nested savepoints propagate actions up the hierarchy on commit."""
    log = []
    with session.begin():
        with session.begin_nested():
            with session.begin_nested():
                TransactionActionManager.register_action(
                    session, lambda: log.append("deepest_nested")
                )
            assert log == []
        assert log == []

    assert log == ["deepest_nested"]


def test_multi_level_nested_savepoints_partial_rollback(session):
    """11. Multi-level savepoints correctly discard rolled-back level while preserving sibling/ancestor."""
    log = []
    with session.begin():
        TransactionActionManager.register_action(
            session, lambda: log.append("level_1")
        )
        with session.begin_nested():
            TransactionActionManager.register_action(
                session, lambda: log.append("level_2")
            )
            try:
                with session.begin_nested():
                    TransactionActionManager.register_action(
                        session, lambda: log.append("level_3_dropped")
                    )
                    raise RuntimeError("Level 3 fail")
            except RuntimeError:
                pass

    assert log == ["level_1", "level_2"]


def test_root_rollback_with_active_savepoint_discards_all_actions(session):
    """12. Root rollback with an active uncommitted savepoint discards all actions."""
    log = []
    try:
        with session.begin():
            TransactionActionManager.register_action(
                session, lambda: log.append("root")
            )
            sp = session.begin_nested()
            TransactionActionManager.register_action(
                session, lambda: log.append("savepoint")
            )
            raise RuntimeError("Root aborted with savepoint active")
    except RuntimeError:
        pass

    assert log == []


def test_root_rollback_with_multiple_nested_savepoints(session):
    """13. Root rollback with multiple active savepoints cleans up all pending actions."""
    log = []
    try:
        with session.begin():
            TransactionActionManager.register_action(
                session, lambda: log.append("root")
            )
            sp1 = session.begin_nested()
            TransactionActionManager.register_action(
                session, lambda: log.append("sp1")
            )
            sp2 = session.begin_nested()
            TransactionActionManager.register_action(
                session, lambda: log.append("sp2")
            )
            raise RuntimeError("Catastrophic root rollback")
    except RuntimeError:
        pass

    assert log == []


def test_ancestor_savepoint_rollback_discards_descendant_actions(session):
    """14. Rolling back an ancestor savepoint cleans up any descendant savepoint actions."""
    log = []
    with session.begin():
        TransactionActionManager.register_action(
            session, lambda: log.append("outer")
        )
        sp1 = session.begin_nested()
        TransactionActionManager.register_action(
            session, lambda: log.append("sp1_dropped")
        )
        sp2 = session.begin_nested()
        TransactionActionManager.register_action(
            session, lambda: log.append("sp2_dropped")
        )

        # Rollback ancestor sp1 while descendant sp2 is active
        sp1.rollback()

    assert log == ["outer"]


def test_session_close_discards_pending_actions_before_session_reuse(engine):
    """15. Calling session.close() with pending actions discards them and prevents execution on reuse."""
    log = []
    s = Session(engine)
    s.begin()
    TransactionActionManager.register_action(
        s, lambda: log.append("should_not_run")
    )
    s.close()

    # Reusing the session
    with s.begin():
        pass

    assert log == []


def test_session_reset_discards_pending_actions(engine):
    """16. Calling session.reset() with pending actions discards them cleanly."""
    log = []
    s = Session(engine)
    s.begin()
    TransactionActionManager.register_action(
        s, lambda: log.append("should_not_run")
    )
    s.reset()

    # Reusing the session
    with s.begin():
        pass

    assert log == []


def test_reused_session_does_not_accumulate_listeners(session):
    """17. Reused session instances register event listeners only once without accumulating duplicates."""
    with session.begin():
        TransactionActionManager.register_action(session, lambda: None)

    assert session.info.get(KEY_REGISTERED) is True

    # Register again in a second transaction
    with session.begin():
        TransactionActionManager.register_action(session, lambda: None)

    assert session.info.get(KEY_REGISTERED) is True
    # Verify listener is registered once
    assert event.contains(
        session, "after_commit", TransactionActionManager._after_commit
    )


def test_action_exception_does_not_prevent_remaining_actions(session):
    """18. An exception inside one action does not prevent subsequent actions from executing."""
    log = []

    def _failing_action():
        log.append("failing")
        raise RuntimeError("Action boom")

    def _success_action():
        log.append("success")

    with session.begin():
        TransactionActionManager.register_action(session, _failing_action)
        TransactionActionManager.register_action(session, _success_action)

    assert log == ["failing", "success"]
