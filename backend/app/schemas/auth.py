from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    organization_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str
    status: str


class UserOut(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    organization_id: Optional[UUID]

    class Config:
        from_attributes = True