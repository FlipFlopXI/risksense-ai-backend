from datetime import date, datetime
from uuid import UUID

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=50)

    @field_validator("password")
    @classmethod
    def password_requirements(cls, value: str) -> str:
        if not (re.search(r"[A-Z]", value) and re.search(r"[0-9]", value)
                and re.search(r"[^A-Za-z0-9\s]", value)):
            raise ValueError("Password must include an uppercase letter, a number, and a special character.")
        return value


class RegistrationEmailRequest(BaseModel):
    email: EmailStr


class RegistrationVerifyRequest(RegistrationEmailRequest):
    code: str = Field(pattern=r"^\d{6}$")


class RegistrationPendingResponse(BaseModel):
    email: EmailStr
    code_length: int = 6
    resend_after_seconds: int = 60


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr


class PasswordRecoveryCompleteRequest(PasswordRecoveryRequest):
    code: str = Field(pattern=r"^\d{6}$")


class PasswordRecoveryResponse(BaseModel):
    message: str
    code_length: int = 6
    resend_after_seconds: int = 60


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: UserRole
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(min_length=20, max_length=4096)


class LogoutRequest(RefreshTokenRequest):
    pass


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_requirements(cls, value: str) -> str:
        return UserRegisterRequest.password_requirements(value)


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    is_current: bool


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: UserRole
    is_active: bool
