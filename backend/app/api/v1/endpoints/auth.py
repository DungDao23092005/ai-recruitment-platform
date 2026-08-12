from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.exceptions import ConflictException
from app.core.security import create_access_token
from app.models import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        user = await AuthService(db).register_user(data)
    except ConflictException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    user = await AuthService(db).authenticate_user(
        email=form_data.username,
        password=form_data.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(subject=str(user.id))
    return Token(access_token=access_token, token_type="bearer")


@router.post("/login/json", response_model=Token)
async def login_json(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> Token:
    user = await AuthService(db).authenticate_user(
        email=data.email,
        password=data.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    access_token = create_access_token(subject=str(user.id))
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserRead:
    return UserRead.model_validate(current_user)
