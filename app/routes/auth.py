"""Authentication routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import api_response, get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.services.auth_service import login as login_service
from app.routes._errors import run_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await run_service(lambda: login_service(payload.username, payload.password, db))


@router.post("/logout")
async def logout():
    return api_response(message="Logout successful")


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return api_response(
        data={
            "id": current_user.id,
            "employee_id": current_user.employee_id,
            "username": current_user.username,
            "role": current_user.role,
            "is_active": current_user.is_active,
        },
        message="Current user loaded",
    )
