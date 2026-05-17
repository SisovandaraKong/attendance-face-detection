"""Attendance and payroll report service."""

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import Attendance
from app.models.payroll import PayrollRun
from app.services import payroll_service


async def attendance_report(month: int, year: int, db: AsyncSession) -> dict:
    """Return attendance rows for a calendar month."""
    result = await db.execute(
        select(Attendance)
        .options(selectinload(Attendance.employee))
        .where(extract("month", Attendance.date) == month, extract("year", Attendance.date) == year)
        .order_by(Attendance.date, Attendance.employee_id)
    )
    rows = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "employee_id": row.employee_id,
                "employee_name": row.employee.name if row.employee else None,
                "date": row.date.isoformat(),
                "status": row.status,
                "clock_in": row.clock_in.isoformat() if row.clock_in else None,
                "clock_out": row.clock_out.isoformat() if row.clock_out else None,
                "work_hours": str(row.work_hours),
            }
            for row in rows
        ],
        "message": "Attendance report loaded",
    }


async def payroll_report(month: int, year: int, db: AsyncSession) -> dict:
    """Return payroll summary for a calendar month if a run exists."""
    run = await db.scalar(select(PayrollRun).where(PayrollRun.month == month, PayrollRun.year == year))
    if run is None:
        return {"success": False, "data": None, "message": "Payroll run not found"}
    return await payroll_service.get_payroll_summary(run.id, db)
