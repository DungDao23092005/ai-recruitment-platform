from typing import AsyncGenerator, Dict, Any, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
from app.core.constants import UserRole
from app.core.exceptions import UnauthorizedException, ForbiddenException

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


async def get_db() -> AsyncGenerator[Any, None]:
    """
    Dependency provider for database session.
    Yields an active database session instance.
    """
    # Placeholder session generator - will be replaced when DB session factory is wired
    try:
        session = None
        yield session
    finally:
        pass


async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Dependency to decode JWT token and retrieve the current authenticated user.
    """
    if not token:
        raise UnauthorizedException("Could not validate credentials")
    
    # Dummy user dict for authentication scaffolding
    return {
        "id": "00000000-0000-0000-0000-000000000000",
        "email": "user@example.com",
        "role": UserRole.CANDIDATE.value,
        "is_active": True
    }


def RoleChecker(allowed_roles: List[UserRole]):
    async def role_dependency(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in [role.value for role in allowed_roles]:
            raise ForbiddenException(
                f"Role '{user_role}' does not have permission to access this resource"
            )
        return current_user
    return role_dependency


require_admin = RoleChecker([UserRole.ADMIN])
require_recruiter = RoleChecker([UserRole.RECRUITER, UserRole.ADMIN])
require_candidate = RoleChecker([UserRole.CANDIDATE, UserRole.ADMIN])
