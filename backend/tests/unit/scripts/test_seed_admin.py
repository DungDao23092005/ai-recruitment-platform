"""Tests for the admin seeder script."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.security import get_password_hash, verify_password
from app.database.session import async_session_factory
from app.domain.enums import UserRole
from app.models import User


class TestSeedAdmin:
    """Tests for the seed_admin script behavior."""

    @pytest.fixture
    def mock_session_factory(self):
        """Mock the async_session_factory to avoid real DB connections."""
        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        return mock_session_factory, mock_session

    def test_case_a_creates_admin_when_missing(self, mock_session_factory):
        """CASE A: admin@example.com does not exist → create the admin user."""
        mock_factory, mock_session = mock_session_factory

        # No existing user
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock commit and refresh
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch("scripts.seed_admin.async_session_factory", mock_factory):
            from scripts.seed_admin import seed_admin

            asyncio.run(seed_admin())

        # Verify user was created with correct attributes
        mock_session.add.assert_called_once()
        added_user = mock_session.add.call_args[0][0]
        assert added_user.email == "admin@example.com"
        assert added_user.role == UserRole.ADMIN
        assert added_user.is_active is True
        assert verify_password("Password123!", added_user.password_hash)

        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()

    def test_case_b_idempotent_when_admin_exists(self, mock_session_factory):
        """CASE B: admin@example.com already exists with role=admin → do not create duplicate."""
        mock_factory, mock_session = mock_session_factory

        # Existing admin user
        existing_user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            password_hash=get_password_hash("Password123!"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing_user
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("scripts.seed_admin.async_session_factory", mock_factory):
            from scripts.seed_admin import seed_admin

            asyncio.run(seed_admin())

        # Verify no new user was created
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_awaited()

    def test_case_c_fails_when_conflicting_role(self, mock_session_factory):
        """CASE C: admin@example.com exists with non-admin role → fail safely."""
        mock_factory, mock_session = mock_session_factory

        # Existing user with non-admin role
        existing_user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            password_hash=get_password_hash("somepassword"),
            role=UserRole.CANDIDATE,
            is_active=True,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing_user
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("scripts.seed_admin.async_session_factory", mock_factory):
            from scripts.seed_admin import seed_admin

            with pytest.raises(RuntimeError) as exc_info:
                asyncio.run(seed_admin())

        assert "Conflict" in str(exc_info.value)
        assert "admin@example.com" in str(exc_info.value)
        assert "candidate" in str(exc_info.value).lower()

        # Verify no modification was attempted
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_awaited()

    def test_password_is_hashed(self):
        """Verify the development password is properly hashed."""
        from scripts.seed_admin import ADMIN_PASSWORD
        from app.core.security import get_password_hash

        hash_result = get_password_hash(ADMIN_PASSWORD)
        assert hash_result != ADMIN_PASSWORD
        assert hash_result.startswith("$")  # bcrypt hash
        assert verify_password(ADMIN_PASSWORD, hash_result)

    def test_does_not_modify_unrelated_users(self, mock_session_factory):
        """Verify seeder only touches the admin account."""
        mock_factory, mock_session = mock_session_factory

        # Existing admin user
        existing_user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            password_hash=get_password_hash("Password123!"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing_user
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("scripts.seed_admin.async_session_factory", mock_factory):
            from scripts.seed_admin import seed_admin

            asyncio.run(seed_admin())

        # Only one execute call for the select query
        assert mock_session.execute.await_count == 1
        mock_session.add.assert_not_called()