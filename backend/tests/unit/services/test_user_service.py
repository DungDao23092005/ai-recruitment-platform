import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException, EntityNotFoundException
from app.domain.enums import UserRole
from app.models import CandidateProfile, RecruiterProfile, User
from app.repositories import UserRepository
from app.schemas.user import CandidateProfileCreate, RecruiterProfileCreate
from app.services.user_service import UserService


def make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_user(user_id: uuid.UUID | None = None) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email=f"{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.CANDIDATE,
    )


def make_service(session) -> UserService:
    service = UserService(session)
    service.users = AsyncMock(spec=UserRepository)
    return service


class TestGetUserById:
    def test_returns_user(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        service.users.get_by_id.return_value = user

        result = asyncio.run(service.get_user_by_id(user.id))

        assert result is user

    def test_returns_none_when_missing(self):
        session = make_session()
        service = make_service(session)
        service.users.get_by_id.return_value = None

        result = asyncio.run(service.get_user_by_id(uuid.uuid4()))

        assert result is None


class TestCreateCandidateProfile:
    def test_creates_profile(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        user.candidate_profile = None
        service.users.get_with_profile.return_value = user
        data = CandidateProfileCreate(
            full_name="Jane Doe",
            phone="0123456789",
            title="Software Engineer",
        )

        profile = asyncio.run(
            service.create_candidate_profile(user_id=user.id, data=data)
        )

        assert isinstance(profile, CandidateProfile)
        assert profile.user_id == user.id
        assert profile.full_name == "Jane Doe"
        assert profile.phone == "0123456789"
        assert profile.title == "Software Engineer"
        session.add.assert_called_once_with(profile)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(profile)

    def test_user_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.users.get_with_profile.return_value = None
        data = CandidateProfileCreate()

        with pytest.raises(EntityNotFoundException):
            asyncio.run(service.create_candidate_profile(user_id=uuid.uuid4(), data=data))

    def test_duplicate_profile_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        user.candidate_profile = CandidateProfile()
        service.users.get_with_profile.return_value = user
        data = CandidateProfileCreate()

        with pytest.raises(ConflictException):
            asyncio.run(service.create_candidate_profile(user_id=user.id, data=data))

    def test_commit_failure_rolls_back(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        user.candidate_profile = None
        service.users.get_with_profile.return_value = user
        session.commit.side_effect = RuntimeError("db down")
        data = CandidateProfileCreate()

        with pytest.raises(RuntimeError):
            asyncio.run(service.create_candidate_profile(user_id=user.id, data=data))

        session.rollback.assert_awaited_once()


class TestCreateRecruiterProfile:
    def test_creates_profile(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        user.recruiter_profile = None
        service.users.get_with_profile.return_value = user
        company_id = uuid.uuid4()
        data = RecruiterProfileCreate(
            full_name="John Doe",
            position="Hiring Manager",
            company_id=company_id,
        )

        profile = asyncio.run(
            service.create_recruiter_profile(user_id=user.id, data=data)
        )

        assert isinstance(profile, RecruiterProfile)
        assert profile.user_id == user.id
        assert profile.company_id == company_id
        assert profile.full_name == "John Doe"
        assert profile.position == "Hiring Manager"
        session.add.assert_called_once_with(profile)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(profile)

    def test_user_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.users.get_with_profile.return_value = None
        data = RecruiterProfileCreate()

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.create_recruiter_profile(user_id=uuid.uuid4(), data=data)
            )

    def test_duplicate_profile_raises_conflict(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        user.recruiter_profile = RecruiterProfile()
        service.users.get_with_profile.return_value = user
        data = RecruiterProfileCreate()

        with pytest.raises(ConflictException):
            asyncio.run(service.create_recruiter_profile(user_id=user.id, data=data))


class TestGetUserWithProfile:
    def test_returns_user(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        service.users.get_with_profile.return_value = user

        result = asyncio.run(service.get_user_with_profile(user.id))

        assert result is user
        service.users.get_with_profile.assert_awaited_once_with(user.id)

    def test_returns_none_when_missing(self):
        session = make_session()
        service = make_service(session)
        service.users.get_with_profile.return_value = None

        result = asyncio.run(service.get_user_with_profile(uuid.uuid4()))

        assert result is None


class TestAttachRecruiterToCompany:
    def test_creates_profile_when_recruiter_has_none(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        user.recruiter_profile = None
        service.users.get_with_profile.return_value = user
        company_id = uuid.uuid4()

        asyncio.run(
            service.attach_recruiter_to_company(user_id=user.id, company_id=company_id)
        )

        session.add.assert_called_once()
        added_profile = session.add.call_args.args[0]
        assert isinstance(added_profile, RecruiterProfile)
        assert added_profile.user_id == user.id
        assert added_profile.company_id == company_id
        session.commit.assert_awaited_once()

    def test_updates_existing_profile_company(self):
        session = make_session()
        service = make_service(session)
        user = make_user()
        profile = RecruiterProfile(user_id=user.id, company_id=uuid.uuid4())
        user.recruiter_profile = profile
        service.users.get_with_profile.return_value = user
        new_company_id = uuid.uuid4()

        asyncio.run(
            service.attach_recruiter_to_company(
                user_id=user.id, company_id=new_company_id
            )
        )

        assert profile.company_id == new_company_id
        session.add.assert_not_called()
        session.commit.assert_awaited_once()

    def test_user_not_found_raises(self):
        session = make_session()
        service = make_service(session)
        service.users.get_with_profile.return_value = None

        with pytest.raises(EntityNotFoundException):
            asyncio.run(
                service.attach_recruiter_to_company(
                    user_id=uuid.uuid4(), company_id=uuid.uuid4()
                )
            )

        session.commit.assert_not_awaited()
