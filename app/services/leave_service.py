"""Leave request and review business logic."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.leave import Leave
from app.models.user import User
from app.services.errors import ConflictError, NotFoundError, ServiceError


VALID_LEAVE_TYPES = {"annual", "sick", "unpaid"}
VALID_LEAVE_STATUSES = {"pending", "approved", "rejected"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _business_days(start: date, end: date) -> Decimal:
    days = [day for day in _date_range(start, end) if day.weekday() < 5]
    return Decimal(len(days))


async def submit_leave_request(
    employee_id: int,
    leave_type: str,
    start_date: date,
    end_date: date,
    reason: str | None,
    db: AsyncSession,
) -> dict:
    """Create a pending leave request for an employee."""
    if leave_type not in VALID_LEAVE_TYPES:
        raise ServiceError("Invalid leave type", status_code=400)
    if start_date > end_date:
        raise ServiceError("Leave start date cannot be after end date", status_code=400)

    employee = await db.get(Employee, employee_id)
    if employee is None or employee.status != "active":
        raise NotFoundError("Active employee not found")

    overlapping = await db.scalar(
        select(Leave).where(
            Leave.employee_id == employee_id,
            Leave.status.in_(("pending", "approved")),
            Leave.start_date <= end_date,
            Leave.end_date >= start_date,
        )
    )
    if overlapping is not None:
        raise ConflictError("Leave request overlaps an existing leave period")

    leave = Leave(
        employee_id=employee_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        total_days=_business_days(start_date, end_date),
        reason=reason,
        status="pending",
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    return {
        "success": True,
        "data": _leave_to_dict(leave),
        "message": "Leave request submitted",
    }


async def approve_leave(leave_id: int, reviewed_by: int, db: AsyncSession) -> dict:
    """Approve a leave request and mark the affected attendance days as leave."""
    leave = await db.get(Leave, leave_id)
    if leave is None:
        raise NotFoundError("Leave request not found")
    if leave.status != "pending":
        raise ConflictError("Only pending leave requests can be approved")

    reviewer = await db.get(User, reviewed_by)
    if reviewer is None or not reviewer.is_active:
        raise NotFoundError("Reviewer not found")

    leave.status = "approved"
    leave.reviewed_by = reviewed_by
    leave.reviewed_at = _utc_now()
    await _mark_attendance_as_leave(leave, db)
    await db.commit()
    await db.refresh(leave)
    return {
        "success": True,
        "data": _leave_to_dict(leave),
        "message": "Leave request approved",
    }


async def reject_leave(leave_id: int, reviewed_by: int, db: AsyncSession) -> dict:
    """Reject a pending leave request."""
    leave = await db.get(Leave, leave_id)
    if leave is None:
        raise NotFoundError("Leave request not found")
    if leave.status != "pending":
        raise ConflictError("Only pending leave requests can be rejected")

    reviewer = await db.get(User, reviewed_by)
    if reviewer is None or not reviewer.is_active:
        raise NotFoundError("Reviewer not found")

    leave.status = "rejected"
    leave.reviewed_by = reviewed_by
    leave.reviewed_at = _utc_now()
    await db.commit()
    await db.refresh(leave)
    return {
        "success": True,
        "data": _leave_to_dict(leave),
        "message": "Leave request rejected",
    }


async def list_leaves(db: AsyncSession, status: str | None = None) -> dict:
    """Return leave requests, optionally filtered by status."""
    stmt = select(Leave).order_by(Leave.start_date.desc(), Leave.id.desc())
    if status is not None:
        if status not in VALID_LEAVE_STATUSES:
            raise ServiceError("Invalid leave status", status_code=400)
        stmt = stmt.where(Leave.status == status)
    result = await db.execute(stmt)
    return {
        "success": True,
        "data": [_leave_to_dict(leave) for leave in result.scalars().all()],
        "message": "Leave requests loaded",
    }


async def list_employee_leaves(employee_id: int, db: AsyncSession) -> dict:
    """Return all leave requests for one employee."""
    result = await db.execute(
        select(Leave)
        .where(Leave.employee_id == employee_id)
        .order_by(Leave.start_date.desc(), Leave.id.desc())
    )
    return {
        "success": True,
        "data": [_leave_to_dict(leave) for leave in result.scalars().all()],
        "message": "Employee leave requests loaded",
    }


async def _mark_attendance_as_leave(leave: Leave, db: AsyncSession) -> None:
    for work_date in _date_range(leave.start_date, leave.end_date):
        if work_date.weekday() >= 5:
            continue

        attendance = await db.scalar(
            select(Attendance).where(
                Attendance.employee_id == leave.employee_id,
                Attendance.date == work_date,
            )
        )
        if attendance is None:
            attendance = Attendance(
                employee_id=leave.employee_id,
                date=work_date,
                work_hours=Decimal("0.00"),
            )
            db.add(attendance)

        if attendance.clock_in is not None or attendance.clock_out is not None:
            continue

        attendance.status = "leave"
        attendance.note = f"{leave.leave_type.title()} leave approved"


def _leave_to_dict(leave: Leave) -> dict:
    return {
        "id": leave.id,
        "employee_id": leave.employee_id,
        "leave_type": leave.leave_type,
        "start_date": leave.start_date.isoformat(),
        "end_date": leave.end_date.isoformat(),
        "total_days": str(leave.total_days),
        "reason": leave.reason,
        "status": leave.status,
        "reviewed_by": leave.reviewed_by,
        "reviewed_at": leave.reviewed_at.isoformat() if leave.reviewed_at else None,
    }
