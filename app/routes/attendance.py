"""Attendance routes."""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.user import User
from app.services import attendance_service
from app.routes._errors import run_service


router = APIRouter(prefix="/api/attendance", tags=["attendance"])


@router.post("/clock-in")
async def clock_in(
    face_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    image_bytes = await face_image.read()
    return await run_service(lambda: attendance_service.clock_in(image_bytes, db))


@router.post("/clock-out")
async def clock_out(
    face_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    image_bytes = await face_image.read()
    return await run_service(lambda: attendance_service.clock_out(image_bytes, db))


@router.get("/today")
async def today_attendance(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: attendance_service.get_today_attendance(db))


@router.get("/{employee_id}")
async def employee_attendance(
    employee_id: int,
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr", "employee")),
):
    return await run_service(lambda: attendance_service.get_employee_attendance(employee_id, month, year, db))
