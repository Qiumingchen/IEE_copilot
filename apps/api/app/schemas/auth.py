from pydantic import BaseModel, ConfigDict, EmailStr

from app.db.models import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    display_name: str | None = None
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
