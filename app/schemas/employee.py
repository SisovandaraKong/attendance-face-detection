"""Employee schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class EmployeeBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    phone: str | None = None
    department: str
    position: str
    salary_type: str = "monthly"
    base_salary: Decimal = Field(gt=0)
    bank_account: str | None = None
    join_date: date
    status: str = "active"


class EmployeeCreate(EmployeeBase):
    username: str | None = None
    temp_password: str = "Temp12345"


class EmployeeUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    department: str | None = None
    position: str | None = None
    salary_type: str | None = None
    base_salary: Decimal | None = Field(default=None, gt=0)
    bank_account: str | None = None
    join_date: date | None = None
    status: str | None = None


class EmployeeRead(EmployeeBase):
    id: int
    face_image_path: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
