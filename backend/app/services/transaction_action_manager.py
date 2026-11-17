"""Transactional action manager for post-commit actions and background dispatches.

Executes actions (sync callbacks or async coroutines) strictly after the root
database transaction successfully commits. Correctly handles SQLAlchemy 2.0
nested transactions (SAVEPOINTs): actions registered inside a SAVEPOINT are promoted
to the parent transaction on nested commit, and discarded on nested rollback.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable, Union

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ActionCallback = Union[Callable[[], Any], Awaitable[Any]]

KEY_ACTIONS = "_tx_action_manager_actions"
KEY_REGISTERED = "_tx_action_manager_registered"


class TransactionActionManager:
    """Manages post-commit actions attached to SQLAlchemy transactions."""

    @classmethod
    def register_action(cls, session: Any, action: ActionCallback) -> None:
        """Register an action to execute only after the root transaction commits.

        Associates the action with the innermost active transaction (nested
        SAVEPOINT if present, otherwise root transaction).
        """
        sync_session = getattr(session, "sync_session", session)
        if not hasattr(sync_session, "info"):
            # Defensive fallback for mocks without session.info
            return

        if not sync_session.info.get(KEY_REGISTERED):
            cls._register_listeners(sync_session)
            sync_session.info[KEY_REGISTERED] = True

        tx = (
            sync_session.get_nested_transaction()
            or sync_session.get_transaction()
        )
        if tx is None or not tx.is_active:
            raise RuntimeError(
                "No active transaction available for action registration"
            )

        actions_map = sync_session.info.setdefault(KEY_ACTIONS, {})
        actions_map.setdefault(tx, []).append(action)

    @classmethod
    def _register_listeners(cls, sync_session: Session) -> None:
        event.listen(sync_session, "after_commit", cls._after_commit)
        event.listen(sync_session, "after_rollback", cls._after_rollback)
        event.listen(sync_session, "after_soft_rollback", cls._after_soft_rollback)
        event.listen(sync_session, "after_transaction_end", cls._after_transaction_end)

    @staticmethod
    def _is_descendant_of(tx: Any, ancestor: Any) -> bool:
        """Check if ``tx`` is a nested descendant of ``ancestor``."""
        curr = getattr(tx, "parent", None)
        while curr is not None:
            if curr is ancestor:
                return True
            curr = getattr(curr, "parent", None)
        return False

    @classmethod
    def _discard_tx_and_descendants(
        cls, actions_map: dict[Any, list[Any]], target_tx: Any
    ) -> None:
        """Discard actions for target_tx and any of its descendant SAVEPOINTs."""
        if not actions_map:
            return
        actions_map.pop(target_tx, None)
        to_remove = [
            tx for tx in actions_map if cls._is_descendant_of(tx, target_tx)
        ]
        for tx in to_remove:
            actions_map.pop(tx, None)

    @classmethod
    def _after_commit(cls, session: Session) -> None:
        actions_map = session.info.get(KEY_ACTIONS)
        if not actions_map:
            return

        nested = session.get_nested_transaction()
        if nested is not None:
            # SAVEPOINT commit: promote actions to parent transaction
            parent = nested.parent
            acts = actions_map.pop(nested, None)
            if acts and parent is not None:
                actions_map.setdefault(parent, []).extend(acts)
            return

        # Root commit: drain all remaining valid actions and clear before dispatch
        to_dispatch = []
        for tx, acts in list(actions_map.items()):
            to_dispatch.extend(acts)
        actions_map.clear()

        for action in to_dispatch:
            cls._dispatch_action(action)

    @classmethod
    def _after_rollback(cls, session: Session) -> None:
        actions_map = session.info.get(KEY_ACTIONS)
        if not actions_map:
            return

        nested = session.get_nested_transaction()
        if nested is not None:
            # Nested rollback: discard only the nested transaction and its descendants
            cls._discard_tx_and_descendants(actions_map, nested)
        else:
            # Root rollback: discard all pending actions
            actions_map.clear()

    @classmethod
    def _after_soft_rollback(
        cls, session: Session, previous_transaction: Any
    ) -> None:
        actions_map = session.info.get(KEY_ACTIONS)
        if not actions_map:
            return

        if (
            previous_transaction is not None
            and getattr(previous_transaction, "parent", None) is not None
        ):
            # Nested soft rollback: discard actions for previous_transaction
            cls._discard_tx_and_descendants(actions_map, previous_transaction)
        else:
            # Root soft rollback
            actions_map.clear()

    @classmethod
    def _after_transaction_end(cls, session: Session, transaction: Any) -> None:
        actions_map = session.info.get(KEY_ACTIONS)
        if not actions_map:
            return

        if getattr(transaction, "parent", None) is None:
            # Root transaction ended (commit, rollback, close, reset): clear all
            actions_map.clear()
        else:
            # If transaction is still in actions_map, it ended without promotion -> discard
            cls._discard_tx_and_descendants(actions_map, transaction)

    @classmethod
    def _dispatch_action(cls, action: ActionCallback) -> None:
        """Execute a single action, isolating exceptions so others continue."""
        try:
            if inspect.isawaitable(action):
                cls._schedule_or_run_coroutine(action)
            elif callable(action):
                result = action()
                if inspect.isawaitable(result):
                    cls._schedule_or_run_coroutine(result)
            else:
                logger.warning(
                    "Unrecognized transaction action type: %r", type(action)
                )
        except Exception as exc:
            logger.error(
                "Transaction action execution failed: %s", exc, exc_info=True
            )

    @classmethod
    def _schedule_or_run_coroutine(cls, coro: Awaitable[Any]) -> None:
        """Execute an awaitable without losing exceptions and without illegal asyncio.run."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            task = loop.create_task(cls._run_coroutine(coro))

            def _on_done(t: asyncio.Task[Any]) -> None:
                try:
                    exc = t.exception()
                    if exc is not None:
                        logger.error(
                            "Async transaction action task raised: %s",
                            exc,
                            exc_info=exc,
                        )
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(
                        "Error inspecting transaction action task: %s", e
                    )

            task.add_done_callback(_on_done)
        else:
            asyncio.run(cls._run_coroutine(coro))

    @staticmethod
    async def _run_coroutine(coro: Awaitable[Any]) -> None:
        """Await coroutine and catch/log any exception."""
        try:
            await coro
        except Exception as exc:
            logger.error(
                "Async transaction action failed: %s", exc, exc_info=True
            )
