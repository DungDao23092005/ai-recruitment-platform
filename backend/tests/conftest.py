import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Add backend directory to Python path so that scripts package can be imported
# The scripts package is at backend/scripts/, so we add the backend directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load test environment variables from .env.test BEFORE any settings import.
# Use override=False so that existing environment variables (e.g., from docker-compose)
# take precedence. This allows:
# - Windows host: .env.test provides 127.0.0.1 defaults
# - Docker container: docker-compose env vars (mssql, redis, qdrant) win
try:
    from dotenv import load_dotenv
    env_test_path = Path(__file__).parent.parent.parent / ".env.test"
    if env_test_path.exists():
        load_dotenv(env_test_path, override=False)
except ImportError:
    pass  # python-dotenv not installed, rely on system environment

# Database isolation: ensure tests ALWAYS run against the test database,
# regardless of what is configured in the local .env file or .env.test.
# This prevents pytest from accidentally dropping the development database.
os.environ["DATABASE_NAME"] = "ai_recruitment_platform_test"

# Integration tests drop/recreate the schema per test, while the FastAPI
# lifespan (and its auto-started email outbox poll loop) is session-scoped.
# Keep the background poller off in tests so it cannot query email_outbox
# during the drop window; delivery tests start their own workers explicitly
# and post-commit signals still dispatch.
os.environ["EMAIL_OUTBOX_ENABLED"] = "false"

# Keep the lifespan analytics rollup from racing the per-test schema reset.
os.environ["ANALYTICS_ROLLUP_ENABLED"] = "false"

# Service-level tests exercise the in-process extractor path (and patch it).
# Process isolation has dedicated tests that construct IsolatedPDFProcessor.
os.environ["PDF_ISOLATION_ENABLED"] = "false"


@pytest.fixture(autouse=True)
def _no_outbound_email():
    """Never contact a real SMTP/HTTP provider from the test suite.

    Subscription lifecycle emails are dispatched in fire-and-forget tasks, so
    without this guard every activation/change/revoke test would open an SMTP
    connection (and pay the retry backoff). Tests that assert email behaviour
    spy on these methods explicitly.
    """
    from app.services.email_service import EmailService

    with patch.object(
        EmailService, "send_email", new=AsyncMock()
    ), patch.object(
        EmailService, "send_password_reset_otp", new=AsyncMock()
    ):
        yield
