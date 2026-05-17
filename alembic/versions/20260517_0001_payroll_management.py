"""create payroll management schema

Revision ID: 20260517_0001
Revises:
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260517_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=40)),
        sa.Column("department", sa.String(length=120), nullable=False),
        sa.Column("position", sa.String(length=120), nullable=False),
        sa.Column("salary_type", sa.String(length=20), nullable=False, server_default="monthly"),
        sa.Column("base_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("bank_account", sa.String(length=80)),
        sa.Column("join_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("face_embedding", postgresql.JSONB()),
        sa.Column("face_image_path", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_employees_email", "employees", ["email"])
    op.create_index("ix_employees_status", "employees", ["status"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), unique=True),
        sa.Column("username", sa.String(length=80), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="employee"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "work_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("work_start", sa.Time(), nullable=False),
        sa.Column("work_end", sa.Time(), nullable=False),
        sa.Column("late_threshold_minutes", sa.Integer(), nullable=False, server_default="15"),
    )

    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("clock_in", sa.DateTime(timezone=True)),
        sa.Column("clock_out", sa.DateTime(timezone=True)),
        sa.Column("work_hours", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="present"),
        sa.Column("clock_in_image_path", sa.Text()),
        sa.Column("clock_out_image_path", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
    )
    op.create_index("ix_attendance_employee_id", "attendance", ["employee_id"])
    op.create_index("ix_attendance_date", "attendance", ["date"])
    op.create_index("ix_attendance_status", "attendance", ["status"])

    op.create_table(
        "leaves",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("leave_type", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("total_days", sa.Numeric(5, 2), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_leaves_employee_id", "leaves", ["employee_id"])
    op.create_index("ix_leaves_status", "leaves", ["status"])

    op.create_table(
        "payroll_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("month", "year", name="uq_payroll_runs_month_year"),
    )
    op.create_index("ix_payroll_runs_status", "payroll_runs", ["status"])

    op.create_table(
        "payroll_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payroll_run_id", sa.Integer(), sa.ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("base_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("overtime_hours", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("overtime_pay", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("late_deduction", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("unpaid_leave_deduction", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("bonus", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net_pay", sa.Numeric(12, 2), nullable=False),
        sa.Column("working_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("present_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text()),
        sa.UniqueConstraint("payroll_run_id", "employee_id", name="uq_payroll_items_run_employee"),
    )
    op.create_index("ix_payroll_items_payroll_run_id", "payroll_items", ["payroll_run_id"])
    op.create_index("ix_payroll_items_employee_id", "payroll_items", ["employee_id"])

    op.create_table(
        "payslips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payroll_item_id", sa.Integer(), sa.ForeignKey("payroll_items.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("pdf_path", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("payslips")
    op.drop_table("payroll_items")
    op.drop_table("payroll_runs")
    op.drop_table("leaves")
    op.drop_table("attendance")
    op.drop_table("work_schedules")
    op.drop_table("users")
    op.drop_table("employees")
