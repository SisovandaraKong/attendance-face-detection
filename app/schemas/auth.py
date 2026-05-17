"""Authentication schemas."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserRead(BaseModel):
    id: int
    employee_id: int | None
    username: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}
