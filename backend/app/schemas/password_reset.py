from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class VerifyResetOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class VerifyResetOtpResponse(BaseModel):
    reset_token: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    reset_token: str
    new_password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)


class ResetPasswordResponse(BaseModel):
    message: str