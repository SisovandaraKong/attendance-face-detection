"""Employee Self-Service portal routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.attendance import Attendance
from app.models.leave import Leave
from app.models.payroll import PayrollItem, PayrollRun
from app.models.user import User

router = APIRouter(prefix="/api/portal", tags=["portal"])


@router.get("/my-summary")
async def my_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the logged-in employee's summary: attendance, leaves, payslips."""
    eid = current_user.employee_id

    # Attendance this month
    from datetime import date
    today = date.today()
    attendance_count = await db.scalar(
        select(func.count(Attendance.id)).where(
            Attendance.employee_id == eid,
            extract("month", Attendance.date) == today.month,
            extract("year", Attendance.date) == today.year,
        )
    ) or 0

    # Leave balances
    approved_leaves = await db.scalar(
        select(func.count(Leave.id)).where(
            Leave.employee_id == eid,
            Leave.status == "approved",
            extract("year", Leave.start_date) == today.year,
        )
    ) or 0

    pending_leaves = await db.scalar(
        select(func.count(Leave.id)).where(
            Leave.employee_id == eid,
            Leave.status == "pending",
        )
    ) or 0

    # Recent payslips
    result = await db.execute(
        select(PayrollItem, PayrollRun)
        .join(PayrollRun, PayrollItem.payroll_run_id == PayrollRun.id)
        .where(PayrollItem.employee_id == eid)
        .order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
        .limit(6)
    )
    payslip_rows = result.all()
    payslips = [
        {
            "month": run.month,
            "year": run.year,
            "gross_salary": float(item.gross_salary),
            "tax_amount": float(item.tax_amount),
            "social_security": float(item.social_security_employee),
            "net_pay": float(item.net_pay),
            "status": run.status,
            "payroll_run_id": run.id,
        }
        for item, run in payslip_rows
    ]

    return {
        "success": True,
        "data": {
            "employee_id": eid,
            "attendance_this_month": attendance_count,
            "approved_leaves_this_year": approved_leaves,
            "pending_leaves": pending_leaves,
            "annual_leave_balance": max(0, 18 - approved_leaves),  # 18 days default
            "payslips": payslips,
        },
    }


@router.get("/my-attendance")
async def my_attendance(
    month: int,
    year: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the logged-in employee's attendance for a given month."""
    result = await db.execute(
        select(Attendance)
        .where(
            Attendance.employee_id == current_user.employee_id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year,
        )
        .order_by(Attendance.date)
    )
    rows = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "date": str(r.date),
                "status": r.status,
                "clock_in": r.clock_in.isoformat() if r.clock_in else None,
                "clock_out": r.clock_out.isoformat() if r.clock_out else None,
                "work_hours": str(r.work_hours),
            }
            for r in rows
        ],
    }


@router.get("/my-leaves")
async def my_leaves(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the logged-in employee's leave requests."""
    result = await db.execute(
        select(Leave)
        .where(Leave.employee_id == current_user.employee_id)
        .order_by(Leave.created_at.desc())
        .limit(20)
    )
    rows = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": r.id,
                "leave_type": r.leave_type,
                "start_date": str(r.start_date),
                "end_date": str(r.end_date),
                "status": r.status,
                "reason": r.reason,
            }
            for r in rows
        ],
    }
