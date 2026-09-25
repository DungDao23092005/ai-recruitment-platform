import os
import sys
from pathlib import Path

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
