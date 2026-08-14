from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.admin import _get_admin_service
from app.domain.enums import ApplicationStatus, UserRole
from app.main import app
from app.models import Application, Company, Job, User
from app.repositories import (
    ApplicationRepository,
    CompanyRepository,
    JobRepository,
    UserRepository,
)
from app.services.admin_service import AdminService


def _admin_stats():
    return {
        "total_users": 5,
        "total_candidates": 2,
        "total_recruiters": 2,
        "total_admins": 1,
        "total_companies": 3,
        "total_jobs": 4,
        "total_applications": 6,
        "applications_by_status": {
            "applied": 2,
            "under_review": 1,
            "shortlisted": 1,
            "interviewing": 1,
            "accepted": 0,
            "rejected": 1,
            "withdrawn": 0,
        },
    }


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.get_stats = AsyncMock(return_value=_admin_stats())
    return service


@pytest.fixture
def client(mock_service):
    app.dependency_overrides[_get_admin_service] = lambda: mock_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _override_user(user):
    async def _override():
        return user

    return _override


def _fake_user(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.is_active = True
    return user


@pytest.fixture
def admin_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _fake_user(UserRole.ADMIN)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def candidate_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _fake_user(UserRole.CANDIDATE)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def recruiter_client(client):
    app.dependency_overrides[get_current_user] = _override_user(
        _fake_user(UserRole.RECRUITER)
    )
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauthorized_client(client):
    async def _override():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.dependency_overrides[get_current_user] = _override
    yield client
    app.dependency_overrides.pop(get_current_user, None)


class TestAdminStatsAuthorization:
    def test_admin_authorized_returns_200(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.status_code == 200
        mock_service.get_stats.assert_awaited_once()

    def test_candidate_forbidden(self, candidate_client, mock_service):
        resp = candidate_client.get("/api/v1/admin/stats")

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.get_stats.assert_not_awaited()

    def test_recruiter_forbidden(self, recruiter_client, mock_service):
        resp = recruiter_client.get("/api/v1/admin/stats")

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        mock_service.get_stats.assert_not_awaited()

    def test_unauthorized_returns_401(self, unauthorized_client, mock_service):
        resp = unauthorized_client.get("/api/v1/admin/stats")

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        mock_service.get_stats.assert_not_awaited()


class TestAdminStatsResponse:
    def test_response_schema_is_correct(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "total_users",
            "total_candidates",
            "total_recruiters",
            "total_admins",
            "total_companies",
            "total_jobs",
            "total_applications",
            "applications_by_status",
        }
        assert set(data["applications_by_status"].keys()) == {
            "applied",
            "under_review",
            "shortlisted",
            "interviewing",
            "accepted",
            "rejected",
            "withdrawn",
        }

    def test_total_users(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.json()["total_users"] == 5

    def test_role_counts(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/stats")

        data = resp.json()
        assert data["total_candidates"] == 2
        assert data["total_recruiters"] == 2
        assert data["total_admins"] == 1

    def test_company_count(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.json()["total_companies"] == 3

    def test_job_count(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.json()["total_jobs"] == 4

    def test_application_count(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.json()["total_applications"] == 6

    def test_applications_by_status(self, admin_client, mock_service):
        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.json()["applications_by_status"]["applied"] == 2
        assert resp.json()["applications_by_status"]["rejected"] == 1

    def test_zero_data(self, admin_client, mock_service):
        mock_service.get_stats.return_value = {
            "total_users": 0,
            "total_candidates": 0,
            "total_recruiters": 0,
            "total_admins": 0,
            "total_companies": 0,
            "total_jobs": 0,
            "total_applications": 0,
            "applications_by_status": {
                "applied": 0,
                "under_review": 0,
                "shortlisted": 0,
                "interviewing": 0,
                "accepted": 0,
                "rejected": 0,
                "withdrawn": 0,
            },
        }

        resp = admin_client.get("/api/v1/admin/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] == 0
        assert data["total_applications"] == 0
        assert data["applications_by_status"]["applied"] == 0


class TestAdminServiceInteraction:
    def test_service_called_with_no_args(self, admin_client, mock_service):
        admin_client.get("/api/v1/admin/stats")

        mock_service.get_stats.assert_awaited_once_with()

    def test_repository_counts_via_service(self, mock_service):
        stats = _admin_stats()
        mock_service.get_stats.return_value = stats

        result = asyncio.run(mock_service.get_stats())

        assert result["total_users"] == stats["total_users"]
        assert (
            result["applications_by_status"]
            == stats["applications_by_status"]
        )


class TestAdminServiceAggregation:
    def make_session(self) -> MagicMock:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        return session

    def make_user(self, role: UserRole) -> User:
        return User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4()}@example.com",
            password_hash="hashed",
            role=role,
            is_active=True,
        )

    def make_application(
        self, status: ApplicationStatus = ApplicationStatus.APPLIED
    ) -> Application:
        return Application(
            id=uuid.uuid4(),
            candidate_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            status=status,
        )

    def make_service(self, session) -> AdminService:
        service = AdminService(session)
        service.users = AsyncMock(spec=UserRepository)
        service.companies = AsyncMock(spec=CompanyRepository)
        service.jobs = AsyncMock(spec=JobRepository)
        service.applications = AsyncMock(spec=ApplicationRepository)
        return service

    def test_aggregates_all_counts(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.list_all.return_value = [
            self.make_user(UserRole.CANDIDATE),
            self.make_user(UserRole.CANDIDATE),
            self.make_user(UserRole.RECRUITER),
            self.make_user(UserRole.ADMIN),
        ]
        service.companies.list_all.return_value = [Company(
            id=uuid.uuid4(), name="C", slug="c", tax_code="t", size="startup"
        )]
        service.jobs.list_all.return_value = [Job(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            title="Dev",
            description="Desc",
            status="published",
            job_type="full_time",
            workplace_type="remote",
            location="",
        )]
        service.applications.list_all.return_value = [
            self.make_application(ApplicationStatus.APPLIED),
            self.make_application(ApplicationStatus.APPLIED),
            self.make_application(ApplicationStatus.UNDER_REVIEW),
            self.make_application(ApplicationStatus.ACCEPTED),
        ]

        result = asyncio.run(service.get_stats())

        assert result.total_users == 4
        assert result.total_candidates == 2
        assert result.total_recruiters == 1
        assert result.total_admins == 1
        assert result.total_companies == 1
        assert result.total_jobs == 1
        assert result.total_applications == 4
        assert result.applications_by_status.applied == 2
        assert result.applications_by_status.under_review == 1
        assert result.applications_by_status.accepted == 1
        assert result.applications_by_status.interviewing == 0
        assert result.applications_by_status.withdrawn == 0

    def test_zero_data_returns_zeroes(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.list_all.return_value = []
        service.companies.list_all.return_value = []
        service.jobs.list_all.return_value = []
        service.applications.list_all.return_value = []

        result = asyncio.run(service.get_stats())

        assert result.total_users == 0
        assert result.total_candidates == 0
        assert result.total_recruiters == 0
        assert result.total_admins == 0
        assert result.total_companies == 0
        assert result.total_jobs == 0
        assert result.total_applications == 0
        assert result.applications_by_status.applied == 0
        assert result.applications_by_status.rejected == 0

    def test_repositories_queried_through_repository_layer(self):
        session = self.make_session()
        service = self.make_service(session)
        service.users.list_all.return_value = []
        service.companies.list_all.return_value = []
        service.jobs.list_all.return_value = []
        service.applications.list_all.return_value = []

        asyncio.run(service.get_stats())

        service.users.list_all.assert_awaited_once()
        service.companies.list_all.assert_awaited_once()
        service.jobs.list_all.assert_awaited_once()
        service.applications.list_all.assert_awaited_once()
