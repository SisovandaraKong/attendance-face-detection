"""Report routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.user import User
from app.services import report_service
from app.routes._errors import run_service


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/attendance")
async def attendance_report(
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: report_service.attendance_report(month, year, db))


@router.get("/payroll")
async def payroll_report(
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: report_service.payroll_report(month, year, db))
