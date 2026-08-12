from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.database.session import get_db_session
from app.domain.enums import UserRole
from app.models import User
from app.services import UserService

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)

_UNAUTHORIZED_DETAIL = "Could not validate credentials"
_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a real AsyncSession from the shared async session factory."""
    async for session in get_db_session():
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the JWT and return the authenticated user.

    Invalid, expired or malformed tokens, a missing/invalid ``sub``, or an
    unknown user all resolve to a 401 without leaking user existence.
    """
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHORIZED_DETAIL,
            headers=_UNAUTHORIZED_HEADERS,
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHORIZED_DETAIL,
            headers=_UNAUTHORIZED_HEADERS,
        )
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHORIZED_DETAIL,
            headers=_UNAUTHORIZED_HEADERS,
        ) from None

    user = await UserService(db).get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHORIZED_DETAIL,
            headers=_UNAUTHORIZED_HEADERS,
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


def require_role(allowed_roles: list[UserRole]):
    """Build a dependency that requires the user's role to be in ``allowed_roles``.

    Membership-only: an admin does not bypass the guard unless ADMIN is
    explicitly listed in ``allowed_roles``.
    """

    async def role_dependency(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return current_user

    return role_dependency


require_admin = require_role([UserRole.ADMIN])
require_recruiter = require_role([UserRole.RECRUITER, UserRole.ADMIN])
require_candidate = require_role([UserRole.CANDIDATE, UserRole.ADMIN])