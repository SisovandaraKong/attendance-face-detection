"""Payroll routes."""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.user import User
from app.services import payroll_service, payslip_service
from app.routes._errors import run_service


router = APIRouter(prefix="/api/payroll", tags=["payroll"])


@router.post("/run")
async def run_payroll(
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: payroll_service.run_payroll(month, year, current_user.id, db))


@router.get("/{payroll_run_id}")
async def payroll_summary(
    payroll_run_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: payroll_service.get_payroll_summary(payroll_run_id, db))


@router.put("/{payroll_run_id}/approve")
async def approve_payroll(
    payroll_run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return await run_service(lambda: payroll_service.approve_payroll(payroll_run_id, current_user.id, db))


@router.get("/{payroll_run_id}/items")
async def payroll_items(
    payroll_run_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: payroll_service.get_payroll_items(payroll_run_id, db))


@router.get("/{payroll_run_id}/payslip/{employee_id}")
async def payslip(
    payroll_run_id: int,
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr", "employee")),
):
    result = await run_service(lambda: payslip_service.generate_employee_payslip(payroll_run_id, employee_id, db))
    return FileResponse(result["data"]["pdf_path"], media_type="application/pdf")
