"""Pydantic schemas for payroll configuration, execution, and reporting."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SalaryConfigCreate(BaseModel):
    employee_id: int = Field(gt=0)
    effective_from: date
    base_salary: float = Field(ge=0)
    overtime_rate_multiplier: float = Field(default=1.5, ge=0)
    transport_allowance: float = Field(default=0, ge=0)
    meal_allowance: float = Field(default=0, ge=0)
    grade: str = Field(min_length=1, max_length=20)
    is_active: bool = True


class SalaryConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    effective_from: date
    base_salary: float
    overtime_rate_multiplier: float
    transport_allowance: float
    meal_allowance: float
    grade: str
    is_active: bool


class DeductionRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rule_type: str = Field(min_length=1, max_length=20)
    value: float = Field(ge=0)
    applies_to_grade: str | None = Field(default=None, max_length=20)
    is_active: bool = True


class DeductionRuleToggleRequest(BaseModel):
    is_active: bool


class DeductionRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rule_type: str
    value: float
    applies_to_grade: str | None = None
    is_active: bool


class PayrollRunRequest(BaseModel):
    period_month: int = Field(ge=1, le=12)
    period_year: int = Field(ge=2000, le=9999)
    employee_ids: list[int] | None = None


class PayrollEmployeeInfo(BaseModel):
    id: int
    employee_code: str
    full_name: str
    branch_name: str | None = None
    department_name: str | None = None


class PayrollRecordResponse(BaseModel):
    id: int
    employee_id: int
    period_month: int
    period_year: int
    working_days_in_period: int
    days_present: int
    days_absent: int
    days_late: int
    total_late_minutes: int
    total_overtime_minutes: int
    base_salary: float
    transport_allowance: float
    meal_allowance: float
    overtime_pay: float
    gross_pay: float
    deductions_json: dict[str, float]
    total_deductions: float
    net_pay: float
    status: str
    approved_by: int | None = None
    approved_at: datetime | None = None
    generated_at: datetime
    employee: PayrollEmployeeInfo


class PayrollSummaryBreakdownItem(BaseModel):
    branch_id: int
    branch_name: str
    department_id: int
    department_name: str
    total_employees: int
    total_gross: float
    total_deductions: float
    total_net: float


class PayrollSummaryResponse(BaseModel):
    total_employees: int
    total_gross: float
    total_deductions: float
    total_net: float
    breakdown: list[PayrollSummaryBreakdownItem]


class PayrollListResponse(BaseModel):
    records: list[PayrollRecordResponse]


class PayrollEnvelopeData(BaseModel):
    payload: Any
