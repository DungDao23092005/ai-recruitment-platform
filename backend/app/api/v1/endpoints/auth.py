from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.exceptions import ConflictException, ForbiddenException
from app.core.security import create_access_token
from app.models import User
from app.schemas.password_reset import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    VerifyResetOtpRequest,
    VerifyResetOtpResponse,
)
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
    except ForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
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


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
)
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    """Request a password reset OTP.
    
    Always returns a generic success message to prevent account enumeration.
    """
    await AuthService(db).forgot_password(data.email)
    return ForgotPasswordResponse(
        message="Nếu tài khoản tồn tại, mã OTP đã được gửi đến email."
    )


@router.post(
    "/verify-reset-otp",
    response_model=VerifyResetOtpResponse,
)
async def verify_reset_otp(
    data: VerifyResetOtpRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyResetOtpResponse:
    """Verify the OTP and return a reset token if valid."""
    reset_token = await AuthService(db).verify_reset_otp(data.email, data.otp)
    if reset_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã OTP không hợp lệ hoặc đã hết hạn",
        )
    return VerifyResetOtpResponse(reset_token=reset_token)


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
)
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordResponse:
    """Reset the user's password using the reset token."""
    if data.new_password != data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu xác nhận không khớp",
        )
    
    success = await AuthService(db).reset_password(data.email, data.reset_token, data.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã đặt lại mật khẩu không hợp lệ hoặc đã hết hạn",
        )
    return ResetPasswordResponse(message="Mật khẩu đã được đặt lại thành công")
