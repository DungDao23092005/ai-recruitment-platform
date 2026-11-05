from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.core.exceptions import (
    WorkspaceRequiredException,
    WorkspaceSelectionRequiredException,
)
from app.domain.enums import UserRole
from app.main import app


def _override_user(role: UserRole):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.is_active = True

    async def _override():
        return user

    return _override


@pytest.fixture
def client():
    async def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = _override_user(
        UserRole.RECRUITER
    )
    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_multiple_memberships_without_header_returns_400(client):
    with patch("app.api.deps.WorkspaceService") as service_cls:
        service_cls.return_value.resolve = AsyncMock(
            side_effect=WorkspaceSelectionRequiredException(
                "Select a company workspace with X-Company-ID"
            )
        )

        response = client.get(
            f"/api/v1/applications/{uuid.uuid4()}"
        )

    assert response.status_code == 400
    assert "X-Company-ID" in response.json()["detail"]


def test_missing_membership_returns_403(client):
    with patch("app.api.deps.WorkspaceService") as service_cls:
        service_cls.return_value.resolve = AsyncMock(
            side_effect=WorkspaceRequiredException(
                "You do not have an active company workspace"
            )
        )

        response = client.get(
            f"/api/v1/applications/{uuid.uuid4()}",
            headers={"X-Company-ID": str(uuid.uuid4())},
        )

    assert response.status_code == 403
