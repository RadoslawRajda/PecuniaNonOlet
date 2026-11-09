from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class RegisterCredentials(LoginCredentials):
    password: str = Field(min_length=8, max_length=128)


class User(BaseModel):
    id: int
    email: EmailStr
    role: Literal["user", "analyst"]


class AuthResponse(BaseModel):
    user: User
    token: str
    token_type: str = "bearer"
    expires_in: int = 7 * 24 * 60 * 60


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordResponse(BaseModel):
    message: str
    reauthentication_required: bool = True
