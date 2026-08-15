from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, EntityNotFoundException
from app.models import CandidateProfile, RecruiterProfile, User
from app.repositories import UserRepository
from app.schemas.user import CandidateProfileCreate, RecruiterProfileCreate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session, User)

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