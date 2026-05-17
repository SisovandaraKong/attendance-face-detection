"""System user model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.leave import Leave
    from app.models.payroll import PayrollRun


class User(Base):
    """Internal login account linked to an employee."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
        unique=True,
    )
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="employee", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    employee: Mapped["Employee | None"] = relationship(back_populates="user")
    created_payroll_runs: Mapped[list["PayrollRun"]] = relationship(
        back_populates="creator",
        foreign_keys="PayrollRun.created_by",
    )
    approved_payroll_runs: Mapped[list["PayrollRun"]] = relationship(
        back_populates="approver",
        foreign_keys="PayrollRun.approved_by",
    )
    reviewed_leaves: Mapped[list["Leave"]] = relationship(back_populates="reviewer")
