import os

# Database isolation: ensure tests ALWAYS run against the test database,
# regardless of what is configured in the local .env file.
# This prevents pytest from accidentally dropping the development database.
os.environ["DATABASE_NAME"] = "ai_recruitment_platform_test"
