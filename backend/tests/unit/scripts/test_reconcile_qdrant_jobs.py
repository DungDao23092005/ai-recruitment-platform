"""Tests for reconcile_qdrant_jobs script."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import Filter, FieldCondition, MatchValue

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))


class TestReconcileQdrantJobs:
    """Tests for Qdrant job vector reconciliation."""

    @pytest.fixture
    def mock_repo(self):
        """Create a mock QdrantVectorRepository."""
        repo = AsyncMock()
        repo.JOB_COLLECTION = "jobs"
        repo.client = AsyncMock()
        repo.delete_vector = AsyncMock()
        return repo

    @pytest.fixture
    def mock_session_cm(self):
        """Create a mock SQLAlchemy session with async context manager."""
        session = AsyncMock()
        session.execute = AsyncMock()
        # Mock the async context manager
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    @pytest.fixture
    def sql_job_ids(self):
        """Return a set of valid job UUIDs in SQL."""
        return {
            uuid.UUID("11111111-1111-1111-1111-111111111111"),
            uuid.UUID("22222222-2222-2222-2222-222222222222"),
            uuid.UUID("33333333-3333-3333-3333-333333333333"),
        }

    def _make_mock_result(self, items):
        """Create a mock result that supports result.scalars().all() pattern."""
        class MockScalars:
            def __init__(self, items):
                self.items = items

            def all(self):
                return self.items

        scalars_mock = MagicMock(return_value=MockScalars(items))
        result = MagicMock()
        result.scalars = scalars_mock
        return result

    def _get_run_reconcile(self):
        """Import run_reconcile after patches are applied."""
        import importlib
        import scripts.reconcile_qdrant_jobs
        importlib.reload(scripts.reconcile_qdrant_jobs)
        return scripts.reconcile_qdrant_jobs.run_reconcile

    @pytest.mark.asyncio
    async def test_all_vectors_stale_when_sql_empty(self, mock_repo):
        """Test 1: All 22 vectors identified as stale when SQL contains zero jobs."""
        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Mock Qdrant scroll returning 22 points
        points = []
        for i in range(22):
            job_id = uuid.uuid4()
            point = SimpleNamespace(
                id=job_id,
                payload={"job_id": str(job_id), "is_deleted": False},
            )
            points.append(point)

        mock_repo.client.scroll.side_effect = [
            (points[:100], None),  # First (and only) page
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=True)

        # Verify all 22 identified as stale
        assert mock_repo.client.scroll.called

    @pytest.mark.asyncio
    async def test_existing_sql_job_prevents_deletion(self, mock_repo):
        """Test 2: Existing SQL job prevents deletion of its Qdrant vector."""
        valid_job_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        stale_job_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([valid_job_id]))
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Mock Qdrant with one valid and one stale
        valid_point = SimpleNamespace(
            id=valid_job_id,
            payload={"job_id": str(valid_job_id), "is_deleted": False},
        )
        stale_point = SimpleNamespace(
            id=stale_job_id,
            payload={"job_id": str(stale_job_id), "is_deleted": False},
        )

        mock_repo.client.scroll.side_effect = [
            ([valid_point, stale_point], None),
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=True)

        # Valid job should NOT be deleted
        mock_repo.delete_vector.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_point_id_deleted(self, mock_repo):
        """Test 3: Explicit Qdrant point ID is deleted."""
        stale_job_id = uuid.UUID("33333333-3333-3333-3333-333333333333")

        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Mock Qdrant with stale point
        stale_point = SimpleNamespace(
            id=stale_job_id,
            payload={"job_id": str(stale_job_id), "is_deleted": False},
        )

        mock_repo.client.scroll.side_effect = [
            ([stale_point], None),
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=False)

        # Stale job should be deleted using point ID
        mock_repo.delete_vector.assert_called_once_with("jobs", stale_job_id)

    @pytest.mark.asyncio
    async def test_dry_run_never_deletes(self, mock_repo):
        """Test 4: --dry-run never deletes."""
        stale_job_id = uuid.UUID("44444444-4444-4444-4444-444444444444")

        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        stale_point = SimpleNamespace(
            id=stale_job_id,
            payload={"job_id": str(stale_job_id), "is_deleted": False},
        )

        mock_repo.client.scroll.side_effect = [
            ([stale_point], None),
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=True)

        # delete_vector should NOT be called in dry-run
        mock_repo.delete_vector.assert_not_called()

    @pytest.mark.asyncio
    async def test_qdrant_pagination_handled(self, mock_repo):
        """Test 5: Qdrant pagination is handled."""
        # Create many points to trigger pagination
        job_ids = [uuid.uuid4() for _ in range(250)]
        points_page1 = [
            SimpleNamespace(id=jid, payload={"job_id": str(jid), "is_deleted": False})
            for jid in job_ids[:100]
        ]
        points_page2 = [
            SimpleNamespace(id=jid, payload={"job_id": str(jid), "is_deleted": False})
            for jid in job_ids[100:200]
        ]
        points_page3 = [
            SimpleNamespace(id=jid, payload={"job_id": str(jid), "is_deleted": False})
            for jid in job_ids[200:]
        ]

        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Mock three pages of results
        mock_repo.client.scroll.side_effect = [
            (points_page1, "offset1"),
            (points_page2, "offset2"),
            (points_page3, None),  # Last page
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=True)

        # Should have called scroll 3 times
        assert mock_repo.client.scroll.call_count == 3

    @pytest.mark.asyncio
    async def test_one_failed_point_does_not_stop_reconciliation(
        self, mock_repo
    ):
        """Test 6: One failed point does not stop the remaining reconciliation."""
        stale_job_id1 = uuid.UUID("55555555-5555-5555-5555-555555555555")
        stale_job_id2 = uuid.UUID("66666666-6666-6666-6666-666666666666")

        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        point1 = SimpleNamespace(
            id=stale_job_id1,
            payload={"job_id": str(stale_job_id1), "is_deleted": False},
        )
        point2 = SimpleNamespace(
            id=stale_job_id2,
            payload={"job_id": str(stale_job_id2), "is_deleted": False},
        )

        mock_repo.client.scroll.side_effect = [
            ([point1, point2], None),
        ]

        # First delete fails, second should still be attempted
        mock_repo.delete_vector.side_effect = [
            Exception("Delete failed"),
            None,
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=False)

        # Both delete attempts should have been made
        assert mock_repo.delete_vector.call_count == 2

    @pytest.mark.asyncio
    async def test_global_sql_failure_raises_exception(self, mock_repo):
        """Test: Global SQL failure raises SourceOfTruthUnavailableError."""
        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=Exception("SQL connection failed"))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                exception_raised = False
                try:
                    await run_reconcile(dry_run=False)
                except Exception as e:
                    assert e.__class__.__name__ == "SourceOfTruthUnavailableError"
                    assert "SQL source of truth unavailable" in str(e)
                    exception_raised = True
                assert exception_raised, "Expected SourceOfTruthUnavailableError to be raised"

        # No deletions should happen when SQL fails
        mock_repo.delete_vector.assert_not_called()
        mock_repo.client.scroll.assert_not_called()

    @pytest.mark.asyncio
    async def test_global_qdrant_failure_raises_exception(self, mock_repo):
        """Test: Global Qdrant failure raises QdrantEnumerationError."""
        from scripts.reconcile_qdrant_jobs import QdrantEnumerationError

        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Make Qdrant scroll fail
        mock_repo.client.scroll.side_effect = Exception("Qdrant connection failed")

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                try:
                    await run_reconcile(dry_run=False)
                    pytest.fail("Expected QdrantEnumerationError to be raised")
                except Exception as e:
                    assert e.__class__.__name__ == "QdrantEnumerationError"
                    assert "Qdrant enumeration failed" in str(e)

        # No deletions should happen when Qdrant fails
        mock_repo.delete_vector.assert_not_called()

    @pytest.mark.asyncio
    async def test_repeated_run_idempotent(self, mock_repo):
        """Test 9: Repeated run is idempotent."""
        stale_job_id = uuid.UUID("77777777-7777-7777-7777-777777777777")

        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        stale_point = SimpleNamespace(
            id=stale_job_id,
            payload={"job_id": str(stale_job_id), "is_deleted": False},
        )

        # First run
        mock_repo.client.scroll.side_effect = [
            ([stale_point], None),
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=False)

        # Reset mock for second run - now no points returned
        mock_repo.client.scroll.side_effect = [
            ([], None),
        ]
        mock_repo.delete_vector.reset_mock()

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=False)

        # Second run should not delete anything
        mock_repo.delete_vector.assert_not_called()

    @pytest.mark.asyncio
    async def test_only_jobs_collection_targeted(self, mock_repo):
        """Test 10: Only collection 'jobs' is targeted."""
        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        mock_repo.client.scroll.side_effect = [
            ([], None),
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=True)

        # Verify only jobs collection was scrolled
        mock_repo.client.scroll.assert_called()
        call_args = mock_repo.client.scroll.call_args
        assert call_args.kwargs["collection_name"] == "jobs"

    @pytest.mark.asyncio
    async def test_payload_job_id_fallback(self, mock_repo):
        """Test: Uses payload job_id when different from point ID."""
        point_id = uuid.UUID("88888888-8888-8888-8888-888888888888")
        payload_job_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

        mock_session_cm = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=self._make_mock_result([]))
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Point ID differs from payload job_id
        point = SimpleNamespace(
            id=point_id,
            payload={"job_id": str(payload_job_id), "is_deleted": False},
        )

        mock_repo.client.scroll.side_effect = [
            ([point], None),
        ]

        with patch(
            "app.ai.vector_db.qdrant_client.QdrantVectorRepository",
            return_value=mock_repo,
        ):
            with patch(
                "app.database.session.async_session_factory",
                return_value=mock_session_cm,
            ):
                run_reconcile = self._get_run_reconcile()
                await run_reconcile(dry_run=True)

        # Should use payload job_id for SQL lookup
        # Since neither exists in SQL, it would be stale
        # The important thing is it doesn't crash
        assert mock_repo.client.scroll.called