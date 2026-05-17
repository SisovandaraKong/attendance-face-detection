"""Leave schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class LeaveCreate(BaseModel):
    employee_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: str | None = None


class LeaveRead(BaseModel):
    id: int
    employee_id: int
    leave_type: str
    start_date: date
    end_date: date
    total_days: Decimal
    reason: str | None
    status: str
    reviewed_by: int | None
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}
