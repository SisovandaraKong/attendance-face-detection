"""Employee model."""

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.attendance import Attendance
    from app.models.leave import Leave
    from app.models.payroll import PayrollItem
    from app.models.user import User


class Employee(TimestampMixin, Base):
    """Employee master record with face enrollment data."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[str] = mapped_column(String(120), nullable=False)
    salary_type: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    base_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    bank_account: Mapped[str | None] = mapped_column(String(80))
    join_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    face_embedding: Mapped[list[float] | None] = mapped_column(JSONB)
    face_image_path: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User | None"] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        uselist=False,
    )
    attendance_records: Mapped[list["Attendance"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    leave_requests: Mapped[list["Leave"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    payroll_items: Mapped[list["PayrollItem"]] = relationship(back_populates="employee")
