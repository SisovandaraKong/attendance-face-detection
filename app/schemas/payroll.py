"""Payroll schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PayrollRunRead(BaseModel):
    id: int
    month: int
    year: int
    status: str
    total_cost: Decimal
    created_by: int
    approved_by: int | None
    approved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PayrollItemRead(BaseModel):
    id: int
    payroll_run_id: int
    employee_id: int
    base_salary: Decimal
    overtime_hours: Decimal
    overtime_pay: Decimal
    late_deduction: Decimal
    unpaid_leave_deduction: Decimal
    bonus: Decimal
    net_pay: Decimal
    working_days: int
    present_days: int
    note: str | None

    model_config = {"from_attributes": True}
