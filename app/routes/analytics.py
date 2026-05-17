"""Advanced reporting & analytics API routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import extract, func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.database import get_db
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.leave import Leave
from app.models.payroll import PayrollItem, PayrollRun
from app.models.user import User

import csv
import io

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/analytics")
async def analytics_dashboard(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard analytics: headcount, attendance stats, payroll cost trends."""
    today = date.today()

    # ── Headcount by department ──
    dept_result = await db.execute(
        select(Employee.department, func.count(Employee.id))
        .where(Employee.status == "active")
        .group_by(Employee.department)
    )
    departments = [
        {"department": dept, "count": count}
        for dept, count in dept_result.all()
    ]

    # ── Total active employees ──
    total_active = await db.scalar(
        select(func.count(Employee.id)).where(Employee.status == "active")
    ) or 0

    # ── This month's attendance summary ──
    att_result = await db.execute(
        select(
            Attendance.status,
            func.count(Attendance.id),
        )
        .where(
            extract("month", Attendance.date) == today.month,
            extract("year", Attendance.date) == today.year,
        )
        .group_by(Attendance.status)
    )
    attendance_summary = {status: count for status, count in att_result.all()}

    # ── Monthly payroll cost trend (last 6 months) ──
    payroll_result = await db.execute(
        select(
            PayrollRun.month,
            PayrollRun.year,
            PayrollRun.total_cost,
            PayrollRun.status,
            func.sum(PayrollItem.tax_amount).label("total_tax"),
            func.sum(PayrollItem.social_security_employee).label("total_nssf_ee"),
            func.sum(PayrollItem.social_security_employer).label("total_nssf_er"),
            func.count(PayrollItem.id).label("employee_count"),
        )
        .join(PayrollItem, PayrollItem.payroll_run_id == PayrollRun.id)
        .group_by(PayrollRun.id)
        .order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
        .limit(6)
    )
    payroll_trends = [
        {
            "month": row.month,
            "year": row.year,
            "total_cost": float(row.total_cost or 0),
            "total_tax": float(row.total_tax or 0),
            "total_nssf_employee": float(row.total_nssf_ee or 0),
            "total_nssf_employer": float(row.total_nssf_er or 0),
            "employee_count": row.employee_count,
            "status": row.status,
        }
        for row in payroll_result.all()
    ]

    # ── Leave summary this year ──
    leave_result = await db.execute(
        select(Leave.leave_type, Leave.status, func.count(Leave.id))
        .where(extract("year", Leave.start_date) == today.year)
        .group_by(Leave.leave_type, Leave.status)
    )
    leave_summary = [
        {"type": ltype, "status": lstatus, "count": count}
        for ltype, lstatus, count in leave_result.all()
    ]

    return {
        "success": True,
        "data": {
            "total_active_employees": total_active,
            "departments": departments,
            "attendance_this_month": attendance_summary,
            "payroll_trends": payroll_trends,
            "leave_summary": leave_summary,
        },
    }


@router.get("/attendance-export")
async def export_attendance_csv(
    month: int = Query(...),
    year: int = Query(...),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export attendance data as CSV."""
    result = await db.execute(
        select(Attendance, Employee.name, Employee.department)
        .join(Employee, Attendance.employee_id == Employee.id)
        .where(
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year,
        )
        .order_by(Attendance.date, Employee.name)
    )
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Employee", "Department", "Status", "Clock In", "Clock Out", "Work Hours"])
    for att, name, dept in rows:
        writer.writerow([
            str(att.date),
            name,
            dept,
            att.status,
            att.clock_in.strftime("%H:%M:%S") if att.clock_in else "",
            att.clock_out.strftime("%H:%M:%S") if att.clock_out else "",
            str(att.work_hours),
        ])
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{year}_{month:02d}.csv"},
    )


@router.get("/payroll-export")
async def export_payroll_csv(
    month: int = Query(...),
    year: int = Query(...),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export payroll data as CSV."""
    result = await db.execute(
        select(PayrollItem, Employee.name, Employee.department)
        .join(Employee, PayrollItem.employee_id == Employee.id)
        .join(PayrollRun, PayrollItem.payroll_run_id == PayrollRun.id)
        .where(PayrollRun.month == month, PayrollRun.year == year)
        .order_by(Employee.name)
    )
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Employee", "Department", "Base Salary", "Overtime Pay",
        "Late Deduction", "Leave Deduction", "Bonus",
        "Gross Salary", "Tax", "NSSF Employee", "NSSF Employer", "Net Pay",
    ])
    for item, name, dept in rows:
        writer.writerow([
            name, dept,
            str(item.base_salary), str(item.overtime_pay),
            str(item.late_deduction), str(item.unpaid_leave_deduction),
            str(item.bonus), str(item.gross_salary), str(item.tax_amount),
            str(item.social_security_employee), str(item.social_security_employer),
            str(item.net_pay),
        ])
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=payroll_{year}_{month:02d}.csv"},
    )
