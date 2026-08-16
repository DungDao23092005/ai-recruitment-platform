from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    EntityNotFoundException,
    ForbiddenException,
)
from app.models import CandidateProfile, Company, RecruiterProfile, User
from app.repositories import CompanyRepository, UserRepository
from app.schemas.user import (
    CandidateProfileCreate,
    CandidateProfileUpdate,
    RecruiterProfileCreate,
    RecruiterProfileUpdate,
)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session, User)
        self.companies = CompanyRepository(session, Company)

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.users.get_by_id(user_id)

    async def get_user_with_profile(self, user_id: uuid.UUID) -> User | None:
        return await self.users.get_with_profile(user_id)

    async def attach_recruiter_to_company(
        self,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Associate a recruiter's profile with a company (ownership link).

        Creates a ``RecruiterProfile`` if the user does not have one yet,
        otherwise updates ``recruiter_profile.company_id``.
        """
        user = await self.users.get_with_profile(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")

        if user.recruiter_profile is None:
            profile = RecruiterProfile(user_id=user_id, company_id=company_id)
            self.session.add(profile)
            try:
                await self.session.commit()
                await self.session.refresh(profile)
            except Exception:
                await self.session.rollback()
                raise
        else:
            user.recruiter_profile.company_id = company_id
            try:
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                raise

    async def create_candidate_profile(
        self,
        user_id: uuid.UUID,
        data: CandidateProfileCreate,
    ) -> CandidateProfile:
        user = await self.users.get_with_profile(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        if user.candidate_profile is not None:
            raise ConflictException(
                f"User {user_id} already has a candidate profile"
            )

        profile = CandidateProfile(
            user_id=user_id,
            full_name=data.full_name,
            phone=data.phone,
            title=data.title,
        )
        self.session.add(profile)
        try:
            await self.session.commit()
            await self.session.refresh(profile)
        except Exception:
            await self.session.rollback()
            raise
        return profile

    async def create_recruiter_profile(
        self,
        user_id: uuid.UUID,
        data: RecruiterProfileCreate,
    ) -> RecruiterProfile:
        user = await self.users.get_with_profile(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        if user.recruiter_profile is not None:
            raise ConflictException(
                f"User {user_id} already has a recruiter profile"
            )

        profile = RecruiterProfile(
            user_id=user_id,
            company_id=data.company_id,
            full_name=data.full_name,
            position=data.position,
        )
        self.session.add(profile)
        try:
            await self.session.commit()
            await self.session.refresh(profile)
        except Exception:
            await self.session.rollback()
            raise
        return profile

    async def get_recruiter_profile(
        self,
        user_id: uuid.UUID,
    ) -> RecruiterProfile | None:
        """Return the recruiter's profile, or ``None`` if it does not exist."""
        user = await self.users.get_with_profile(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        return user.recruiter_profile

    async def get_candidate_profile(
        self,
        user_id: uuid.UUID,
    ) -> CandidateProfile | None:
        """Return the candidate's profile, or ``None`` if it does not exist."""
        user = await self.users.get_with_profile(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")
        return user.candidate_profile

    async def upsert_candidate_profile(
        self,
        user_id: uuid.UUID,
        data: CandidateProfileUpdate,
    ) -> CandidateProfile:
        """Create or update a candidate's profile (upsert).

        The profile is always tied to the authenticated user's ``user_id``;
        it never accepts a target ``user_id`` from the request body.
        """
        user = await self.users.get_with_profile(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")

        if user.candidate_profile is None:
            profile = CandidateProfile(
                user_id=user_id,
                full_name=data.full_name,
                phone=data.phone,
                title=data.title,
            )
            self.session.add(profile)
            try:
                await self.session.commit()
                await self.session.refresh(profile)
            except Exception:
                await self.session.rollback()
                raise
            return profile

        profile = user.candidate_profile
        profile.full_name = data.full_name
        profile.phone = data.phone
        profile.title = data.title
        try:
            await self.session.commit()
            await self.session.refresh(profile)
        except Exception:
            await self.session.rollback()
            raise
        return profile

    async def upsert_recruiter_profile(
        self,
        user_id: uuid.UUID,
        data: RecruiterProfileUpdate,
    ) -> RecruiterProfile:
        """Create or update a recruiter's profile (upsert).

        ``company_id`` is only accepted when it references a company that the
        recruiter already owns (per the existing ownership model). Recruiter A
        must never link Recruiter B's company.
        """
        user = await self.users.get_with_profile(user_id)
        if user is None:
            raise EntityNotFoundException(f"User {user_id} not found")

        if data.company_id is not None:
            company = await self.companies.get_by_id(data.company_id)
            if company is None:
                raise EntityNotFoundException(
                    f"Company {data.company_id} not found"
                )

            profile = user.recruiter_profile
            owned_company_id = profile.company_id if profile is not None else None
            if owned_company_id is None or owned_company_id != data.company_id:
                raise ForbiddenException(
                    f"Recruiter {user_id} is not allowed to link "
                    f"company {data.company_id}"
                )

        if user.recruiter_profile is None:
            profile = RecruiterProfile(
                user_id=user_id,
                company_id=data.company_id,
                full_name=data.full_name,
                position=data.position,
            )
            self.session.add(profile)
            try:
                await self.session.commit()
                await self.session.refresh(profile)
            except Exception:
                await self.session.rollback()
                raise
            return profile

        profile = user.recruiter_profile
        profile.company_id = data.company_id
        profile.full_name = data.full_name
        profile.position = data.position
        try:
            await self.session.commit()
            await self.session.refresh(profile)
        except Exception:
            await self.session.rollback()
            raise
        return profile