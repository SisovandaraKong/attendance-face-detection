"""Dashboard summary service."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.leave import Leave


async def get_summary(db: AsyncSession) -> dict:
    """Return high-level operational counters for the dashboard."""
    employees = await db.scalar(select(func.count(Employee.id)).where(Employee.status == "active"))
    present_today = await db.scalar(
        select(func.count(Attendance.id)).where(
            Attendance.date == date.today(),
            Attendance.status.in_(["present", "late"]),
        )
    )
    pending_leaves = await db.scalar(select(func.count(Leave.id)).where(Leave.status == "pending"))
    return {
        "success": True,
        "data": {
            "active_employees": employees or 0,
            "present_today": present_today or 0,
            "pending_leaves": pending_leaves or 0,
        },
        "message": "Dashboard summary loaded",
    }
