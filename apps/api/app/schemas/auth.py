from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import UserRole


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    local_part, separator, domain = email.partition("@")
    if not separator or not local_part or not domain or "." not in domain:
        raise ValueError("invalid email address")
    return email


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str
    display_name: str | None = None

    _normalize_email = field_validator("email")(normalize_email)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str

    _normalize_email = field_validator("email")(normalize_email)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
