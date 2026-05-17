"""Dashboard API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.user import User
from app.services import attendance_service, dashboard_service
from app.routes._errors import run_service


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: dashboard_service.get_summary(db))


@router.get("/attendance-today")
async def attendance_today(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: attendance_service.get_today_attendance(db))
