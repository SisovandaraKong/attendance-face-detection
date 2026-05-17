"""Attendance schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class AttendanceRead(BaseModel):
    id: int
    employee_id: int
    date: date
    clock_in: datetime | None
    clock_out: datetime | None
    work_hours: Decimal
    status: str
    clock_in_image_path: str | None
    clock_out_image_path: str | None
    note: str | None

    model_config = {"from_attributes": True}
