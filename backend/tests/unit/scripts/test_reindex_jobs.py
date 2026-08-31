import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlalchemy import select

from app.models import Job
from app.services.job_service import JobService
from scripts.reindex_jobs import run_reindex


@pytest.fixture
def mock_session_factory():
    with patch("scripts.reindex_jobs.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session
        yield mock_session


@pytest.fixture
def mock_job_service():
    with patch("scripts.reindex_jobs.JobService") as mock_service_class:
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        yield mock_service


@pytest.mark.asyncio
async def test_reindex_one_job(mock_session_factory, mock_job_service):
    """Test 1: Reindex one job correctly."""
    mock_session_factory.scalar.return_value = 1
    job = MagicMock(spec=Job)
    job.id = uuid.uuid4()
    mock_job_service.jobs.list_all_jobs.return_value = [job]
    
    await run_reindex(dry_run=False)
    
    mock_job_service._reindex_job.assert_called_once_with(job)


@pytest.mark.asyncio
async def test_reindex_soft_deleted_excluded(mock_session_factory, mock_job_service):
    """Test 5: Soft deleted jobs are excluded from the count and processing."""
    mock_session_factory.scalar.return_value = 0
    await run_reindex(dry_run=False)
    
    # Verify the count statement explicitly filters out deleted jobs
    count_call = mock_session_factory.scalar.call_args[0][0]
    # Check string representation of the SQL statement contains is_deleted = false
    assert "is_deleted = false" in str(count_call.compile(compile_kwargs={"literal_binds": True})).lower()
    
    mock_job_service._reindex_job.assert_not_called()


@pytest.mark.asyncio
async def test_idempotency_multiple_runs(mock_session_factory, mock_job_service):
    """Test 6: Idempotency. Repeated runs process the same job IDs."""
    mock_session_factory.scalar.return_value = 1
    job = MagicMock(spec=Job)
    job.id = uuid.uuid4()
    mock_job_service.jobs.list_all_jobs.return_value = [job]
    
    await run_reindex(dry_run=False)
    await run_reindex(dry_run=False)
    
    # Should call it exactly twice for the exact same job object
    assert mock_job_service._reindex_job.call_count == 2
    mock_job_service._reindex_job.assert_has_calls([call(job), call(job)])


@pytest.mark.asyncio
async def test_batch_processing(mock_session_factory, mock_job_service):
    """Test 7: Verify it paginates if total_jobs > batch_size."""
    mock_session_factory.scalar.return_value = 120
    
    # Mock return 50 jobs for first call, 50 for second, 20 for third
    batch_1 = [MagicMock(spec=Job)] * 50
    batch_2 = [MagicMock(spec=Job)] * 50
    batch_3 = [MagicMock(spec=Job)] * 20
    mock_job_service.jobs.list_all_jobs.side_effect = [batch_1, batch_2, batch_3]
    
    await run_reindex(dry_run=False)
    
    assert mock_job_service.jobs.list_all_jobs.call_count == 3
    assert mock_job_service._reindex_job.call_count == 120


@pytest.mark.asyncio
async def test_reindex_continue_on_error(mock_session_factory, mock_job_service):
    """Test 8: If one job fails, the script should catch the error and continue."""
    mock_session_factory.scalar.return_value = 2
    
    job1 = MagicMock(spec=Job)
    job1.id = uuid.uuid4()
    
    job2 = MagicMock(spec=Job)
    job2.id = uuid.uuid4()
    
    mock_job_service.jobs.list_all_jobs.return_value = [job1, job2]
    mock_job_service._reindex_job.side_effect = [Exception("Qdrant Error"), None]

    await run_reindex(dry_run=False)

    assert mock_job_service._reindex_job.call_count == 2
    mock_job_service._reindex_job.assert_has_calls([call(job1), call(job2)])
