"""Payroll run, payroll item, and payslip models."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.user import User


class PayrollRun(Base):
    """Monthly payroll batch."""

    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("month", "year", name="uq_payroll_runs_month_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    creator: Mapped["User"] = relationship(
        back_populates="created_payroll_runs",
        foreign_keys=[created_by],
    )
    approver: Mapped["User | None"] = relationship(
        back_populates="approved_payroll_runs",
        foreign_keys=[approved_by],
    )
    items: Mapped[list["PayrollItem"]] = relationship(
        back_populates="payroll_run",
        cascade="all, delete-orphan",
    )


class PayrollItem(Base):
    """Calculated payroll amount for one employee in one payroll run."""

    __tablename__ = "payroll_items"
    __table_args__ = (
        UniqueConstraint("payroll_run_id", "employee_id", name="uq_payroll_items_run_employee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payroll_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    overtime_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    late_deduction: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    unpaid_leave_deduction: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    bonus: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    gross_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    social_security_employee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    social_security_employer: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    net_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    working_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    present_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text)

    payroll_run: Mapped["PayrollRun"] = relationship(back_populates="items")
    employee: Mapped["Employee"] = relationship(back_populates="payroll_items")
    payslip: Mapped["Payslip | None"] = relationship(
        back_populates="payroll_item",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Payslip(Base):
    """Generated PDF payslip file for a payroll item."""

    __tablename__ = "payslips"

    id: Mapped[int] = mapped_column(primary_key=True)
    payroll_item_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    payroll_item: Mapped["PayrollItem"] = relationship(back_populates="payslip")
