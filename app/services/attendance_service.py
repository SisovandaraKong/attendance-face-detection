"""Attendance clock-in and clock-out business logic."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import os

import cv2
import numpy as np
from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance, WorkSchedule
from app.services.errors import ConflictError, NotFoundError, ServiceError
from app.services.face_service import identify_employee


ATTENDANCE_IMAGE_DIR = Path(os.getenv("ATTENDANCE_IMAGE_DIR", "storage/attendance"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _combine_today(work_time: time, now: datetime) -> datetime:
    return datetime.combine(now.date(), work_time, tzinfo=now.tzinfo)


async def get_default_schedule(db: AsyncSession) -> WorkSchedule:
    """Return the default schedule, creating the standard one if missing."""
    result = await db.execute(select(WorkSchedule).order_by(WorkSchedule.id).limit(1))
    schedule = result.scalar_one_or_none()
    if schedule is not None:
        return schedule

    schedule = WorkSchedule(
        name="Standard",
        work_start=time(hour=8),
        work_end=time(hour=17),
        late_threshold_minutes=15,
    )
    db.add(schedule)
    await db.flush()
    return schedule


def _save_attendance_image(image_bytes: bytes, employee_id: int, action: str, when: datetime) -> str:
    ATTENDANCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = ATTENDANCE_IMAGE_DIR / f"{employee_id}-{when:%Y%m%d%H%M%S}-{action}.jpg"
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ServiceError("Invalid attendance image", status_code=400)
    if not cv2.imwrite(str(path), image):
        raise ServiceError("Failed to save attendance image", status_code=500)
    return str(path)


async def clock_in(image_bytes: bytes, db: AsyncSession) -> dict:
    """Identify an employee from a camera image and create today's attendance record."""
    match = await identify_employee(image_bytes, db)
    if match is None:
        raise NotFoundError("Face not recognized")

    employee_id = int(match["employee_id"])
    now = _utc_now()
    today = now.date()

    existing = await db.scalar(
        select(Attendance).where(
            Attendance.employee_id == employee_id,
            Attendance.date == today,
        )
    )
    if existing is not None and existing.clock_in is not None:
        raise ConflictError("Employee already clocked in today")

    schedule = await get_default_schedule(db)
    late_after = _combine_today(schedule.work_start, now) + timedelta(
        minutes=schedule.late_threshold_minutes
    )
    status = "late" if now > late_after else "present"
    image_path = _save_attendance_image(image_bytes, employee_id, "clock-in", now)

    if existing is not None and existing.status == "leave":
        raise ConflictError("Employee is marked as on leave today")

    attendance = existing or Attendance(
        employee_id=employee_id,
        date=today,
        work_hours=Decimal("0.00"),
    )
    attendance.clock_in = now
    attendance.status = status
    attendance.clock_in_image_path = image_path
    attendance.note = None
    db.add(attendance)
    await db.commit()
    await db.refresh(attendance)

    return {
        "success": True,
        "data": {
            "attendance_id": attendance.id,
            "employee_id": employee_id,
            "name": match["name"],
            "similarity": match["similarity"],
            "status": attendance.status,
            "clock_in": attendance.clock_in.isoformat() if attendance.clock_in else None,
        },
        "message": "Clock-in recorded",
    }


async def clock_out(image_bytes: bytes, db: AsyncSession) -> dict:
    """Identify an employee and close today's open attendance record."""
    match = await identify_employee(image_bytes, db)
    if match is None:
        raise NotFoundError("Face not recognized")

    employee_id = int(match["employee_id"])
    now = _utc_now()
    attendance = await db.scalar(
        select(Attendance).where(
            Attendance.employee_id == employee_id,
            Attendance.date == now.date(),
        )
    )
    if attendance is None or attendance.clock_in is None:
        raise NotFoundError("No open clock-in record found for today")
    if attendance.clock_out is not None:
        raise ConflictError("Employee already clocked out today")

    image_path = _save_attendance_image(image_bytes, employee_id, "clock-out", now)
    elapsed_hours = Decimal(str((now - attendance.clock_in).total_seconds() / 3600))
    attendance.clock_out = now
    attendance.work_hours = _money(elapsed_hours)
    attendance.clock_out_image_path = image_path
    await db.commit()
    await db.refresh(attendance)

    schedule = await get_default_schedule(db)
    standard_hours = Decimal(
        str(
            (
                datetime.combine(now.date(), schedule.work_end)
                - datetime.combine(now.date(), schedule.work_start)
            ).total_seconds()
            / 3600
        )
    )
    overtime_hours = max(attendance.work_hours - standard_hours, Decimal("0.00"))

    return {
        "success": True,
        "data": {
            "attendance_id": attendance.id,
            "employee_id": employee_id,
            "name": match["name"],
            "similarity": match["similarity"],
            "clock_out": attendance.clock_out.isoformat(),
            "work_hours": str(attendance.work_hours),
            "overtime_hours": str(_money(overtime_hours)),
        },
        "message": "Clock-out recorded",
    }


async def get_today_attendance(db: AsyncSession) -> dict:
    """Return all attendance rows for the current date."""
    today = _utc_now().date()
    result = await db.execute(
        select(Attendance)
        .where(Attendance.date == today)
        .order_by(Attendance.clock_in.asc().nulls_last(), Attendance.employee_id)
    )
    rows = result.scalars().all()
    return {
        "success": True,
        "data": [_attendance_to_dict(row) for row in rows],
        "message": "Today's attendance loaded",
    }


async def get_employee_attendance(
    employee_id: int,
    month: int,
    year: int,
    db: AsyncSession,
) -> dict:
    """Return one employee's attendance for a month."""
    result = await db.execute(
        select(Attendance)
        .where(
            Attendance.employee_id == employee_id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year,
        )
        .order_by(Attendance.date)
    )
    rows = result.scalars().all()
    return {
        "success": True,
        "data": [_attendance_to_dict(row) for row in rows],
        "message": "Attendance loaded",
    }


def _attendance_to_dict(attendance: Attendance) -> dict:
    return {
        "id": attendance.id,
        "employee_id": attendance.employee_id,
        "date": attendance.date.isoformat(),
        "clock_in": attendance.clock_in.isoformat() if attendance.clock_in else None,
        "clock_out": attendance.clock_out.isoformat() if attendance.clock_out else None,
        "work_hours": str(attendance.work_hours),
        "status": attendance.status,
        "clock_in_image_path": attendance.clock_in_image_path,
        "clock_out_image_path": attendance.clock_out_image_path,
        "note": attendance.note,
    }
