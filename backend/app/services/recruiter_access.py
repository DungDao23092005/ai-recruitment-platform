from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import UserRole
from app.models import RecruiterProfile, User


async def ensure_recruiter_access(
    session: AsyncSession,
    user: User,
) -> None:
    """Ensure user has recruiter access by transitioning role and creating profile if needed.

    This is called within an existing transaction where the user row is already locked.
    Does not commit independently.

    Behavior:
    - CANDIDATE -> RECRUITER + create RecruiterProfile if not exists
    - RECRUITER -> keep role, ensure profile exists (reuse existing)
    - ADMIN -> no change (do not downgrade, do not create profile)

    This function explicitly queries RecruiterProfile by user_id to avoid
    async SQLAlchemy lazy-loading issues (MissingGreenletException).
    """
    if user.role == UserRole.CANDIDATE:
        user.role = UserRole.RECRUITER
        # Explicitly check for existing profile by user_id
        profile = await _get_recruiter_profile_by_user_id(session, user.id)
        if profile is None:
            profile = RecruiterProfile(user_id=user.id)
            session.add(profile)
    elif user.role == UserRole.RECRUITER:
        # Ensure profile exists for existing recruiters
        profile = await _get_recruiter_profile_by_user_id(session, user.id)
        if profile is None:
            profile = RecruiterProfile(user_id=user.id)
            session.add(profile)
    # ADMIN: no change, no profile creation


async def _get_recruiter_profile_by_user_id(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> Optional[RecruiterProfile]:
    """Get RecruiterProfile by user_id without triggering lazy loading."""
    stmt = select(RecruiterProfile).where(
        RecruiterProfile.user_id == user_id,
        RecruiterProfile.is_deleted == False,  # noqa: E712
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()