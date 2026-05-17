"""Monthly payroll calculation and approval service."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import os

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import Attendance, WorkSchedule
from app.models.employee import Employee
from app.models.leave import Leave
from app.models.payroll import PayrollItem, PayrollRun
from app.models.user import User
from app.services.errors import ConflictError, NotFoundError, ServiceError


LATE_PENALTY_AMOUNT = Decimal(os.getenv("LATE_PENALTY_AMOUNT", "5.00"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def working_days_in_month(month: int, year: int) -> int:
    """Count weekdays in a calendar month."""
    _validate_month_year(month, year)
    _, last_day = calendar.monthrange(year, month)
    return sum(
        1 for day in range(1, last_day + 1) if date(year, month, day).weekday() < 5
    )


async def calculate_payroll_item(
    employee: Employee,
    month: int,
    year: int,
    db: AsyncSession,
    bonus: Decimal | int | float = Decimal("0.00"),
) -> PayrollItem:
    """Calculate one employee payroll item without committing it."""
    _validate_month_year(month, year)
    working_days = working_days_in_month(month, year)
    daily_rate = _money(employee.base_salary / Decimal(working_days))

    attendance_rows = await _attendance_for_employee(employee.id, month, year, db)
    present_rows = [row for row in attendance_rows if row.status in {"present", "late"}]
    present_days = len(present_rows)
    late_count = len([row for row in attendance_rows if row.status == "late"])
    overtime_hours = await _calculate_overtime_hours(present_rows, db)
    unpaid_leave_days = await _unpaid_leave_days(employee.id, month, year, db)

    overtime_pay = _money(overtime_hours * (daily_rate / Decimal("8")) * Decimal("1.5"))
    late_deduction = _money(Decimal(late_count) * LATE_PENALTY_AMOUNT)
    unpaid_leave_deduction = _money(unpaid_leave_days * daily_rate)
    bonus_amount = _money(bonus)
    base_salary = _money(employee.base_salary)
    net_pay = _money(
        base_salary + overtime_pay + bonus_amount - late_deduction - unpaid_leave_deduction
    )

    return PayrollItem(
        employee_id=employee.id,
        base_salary=base_salary,
        overtime_hours=_money(overtime_hours),
        overtime_pay=overtime_pay,
        late_deduction=late_deduction,
        unpaid_leave_deduction=unpaid_leave_deduction,
        bonus=bonus_amount,
        net_pay=net_pay,
        working_days=working_days,
        present_days=present_days,
        note=(
            f"late_count={late_count}; unpaid_leave_days={unpaid_leave_days}; "
            f"daily_rate={daily_rate}"
        ),
    )


async def run_payroll(month: int, year: int, created_by: int, db: AsyncSession) -> dict:
    """Create a monthly payroll run for all active employees."""
    _validate_month_year(month, year)

    creator = await db.get(User, created_by)
    if creator is None or not creator.is_active:
        raise NotFoundError("Payroll creator not found")

    existing = await db.scalar(
        select(PayrollRun).where(PayrollRun.month == month, PayrollRun.year == year)
    )
    if existing is not None:
        raise ConflictError("Payroll for this month already exists")

    employees = (
        await db.execute(
            select(Employee)
            .where(Employee.status == "active")
            .order_by(Employee.department, Employee.name)
        )
    ).scalars().all()
    if not employees:
        raise ServiceError("No active employees found for payroll", status_code=400)

    payroll_run = PayrollRun(
        month=month,
        year=year,
        status="draft",
        total_cost=Decimal("0.00"),
        created_by=created_by,
    )
    db.add(payroll_run)
    await db.flush()

    total_cost = Decimal("0.00")
    for employee in employees:
        item = await calculate_payroll_item(employee, month, year, db)
        item.payroll_run_id = payroll_run.id
        total_cost += item.net_pay
        db.add(item)

    payroll_run.total_cost = _money(total_cost)
    await db.commit()
    await db.refresh(payroll_run)
    return {
        "success": True,
        "data": await _payroll_run_to_dict(payroll_run.id, db),
        "message": "Payroll run created",
    }


async def approve_payroll(payroll_run_id: int, approved_by: int, db: AsyncSession) -> dict:
    """Approve a draft or submitted payroll run."""
    payroll_run = await db.get(PayrollRun, payroll_run_id)
    if payroll_run is None:
        raise NotFoundError("Payroll run not found")
    if payroll_run.status not in {"draft", "submitted"}:
        raise ConflictError("Only draft or submitted payroll can be approved")

    approver = await db.get(User, approved_by)
    if approver is None or not approver.is_active:
        raise NotFoundError("Approver not found")

    payroll_run.status = "approved"
    payroll_run.approved_by = approved_by
    payroll_run.approved_at = _utc_now()
    await db.commit()
    await db.refresh(payroll_run)
    return {
        "success": True,
        "data": await _payroll_run_to_dict(payroll_run.id, db),
        "message": "Payroll approved",
    }


async def get_payroll_summary(payroll_run_id: int, db: AsyncSession) -> dict:
    """Return aggregate totals for a payroll run."""
    payroll_run = await db.get(PayrollRun, payroll_run_id)
    if payroll_run is None:
        raise NotFoundError("Payroll run not found")

    result = await db.execute(
        select(
            func.count(PayrollItem.id),
            func.coalesce(func.sum(PayrollItem.base_salary), 0),
            func.coalesce(func.sum(PayrollItem.overtime_pay), 0),
            func.coalesce(func.sum(PayrollItem.late_deduction), 0),
            func.coalesce(func.sum(PayrollItem.unpaid_leave_deduction), 0),
            func.coalesce(func.sum(PayrollItem.bonus), 0),
            func.coalesce(func.sum(PayrollItem.net_pay), 0),
        ).where(PayrollItem.payroll_run_id == payroll_run_id)
    )
    (
        employee_count,
        gross_salary,
        overtime_pay,
        late_deduction,
        unpaid_leave_deduction,
        bonus,
        net_pay,
    ) = result.one()

    return {
        "success": True,
        "data": {
            "payroll_run": await _payroll_run_to_dict(payroll_run_id, db, include_items=False),
            "employee_count": int(employee_count),
            "gross_salary": str(_money(gross_salary)),
            "overtime_pay": str(_money(overtime_pay)),
            "late_deduction": str(_money(late_deduction)),
            "unpaid_leave_deduction": str(_money(unpaid_leave_deduction)),
            "bonus": str(_money(bonus)),
            "net_pay": str(_money(net_pay)),
        },
        "message": "Payroll summary loaded",
    }


async def get_payroll_items(payroll_run_id: int, db: AsyncSession) -> dict:
    """Return payroll items for a run."""
    payroll_run = await db.get(PayrollRun, payroll_run_id)
    if payroll_run is None:
        raise NotFoundError("Payroll run not found")

    result = await db.execute(
        select(PayrollItem)
        .options(selectinload(PayrollItem.employee))
        .where(PayrollItem.payroll_run_id == payroll_run_id)
        .order_by(PayrollItem.employee_id)
    )
    return {
        "success": True,
        "data": [_payroll_item_to_dict(item) for item in result.scalars().all()],
        "message": "Payroll items loaded",
    }


async def _attendance_for_employee(
    employee_id: int,
    month: int,
    year: int,
    db: AsyncSession,
) -> list[Attendance]:
    result = await db.execute(
        select(Attendance).where(
            Attendance.employee_id == employee_id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year,
        )
    )
    return list(result.scalars().all())


async def _calculate_overtime_hours(rows: list[Attendance], db: AsyncSession) -> Decimal:
    schedule = await _get_default_schedule(db)
    standard_hours = Decimal(
        str(
            (
                datetime.combine(date.today(), schedule.work_end)
                - datetime.combine(date.today(), schedule.work_start)
            ).total_seconds()
            / 3600
        )
    )
    overtime = Decimal("0.00")
    for row in rows:
        overtime += max(Decimal(row.work_hours or 0) - standard_hours, Decimal("0.00"))
    return overtime


async def _unpaid_leave_days(
    employee_id: int,
    month: int,
    year: int,
    db: AsyncSession,
) -> Decimal:
    _, last_day = calendar.monthrange(year, month)
    period_start = date(year, month, 1)
    period_end = date(year, month, last_day)
    result = await db.execute(
        select(Leave).where(
            Leave.employee_id == employee_id,
            Leave.leave_type == "unpaid",
            Leave.status == "approved",
            Leave.start_date <= period_end,
            Leave.end_date >= period_start,
        )
    )
    total = Decimal("0.00")
    for leave in result.scalars().all():
        overlap_start = max(leave.start_date, period_start)
        overlap_end = min(leave.end_date, period_end)
        total += Decimal(
            sum(
                1
                for day_offset in range((overlap_end - overlap_start).days + 1)
                if (overlap_start + timedelta(days=day_offset)).weekday() < 5
            )
        )
    return total


async def _get_default_schedule(db: AsyncSession) -> WorkSchedule:
    schedule = await db.scalar(select(WorkSchedule).order_by(WorkSchedule.id).limit(1))
    if schedule is None:
        schedule = WorkSchedule(
            name="Standard",
            work_start=datetime.strptime("08:00", "%H:%M").time(),
            work_end=datetime.strptime("17:00", "%H:%M").time(),
            late_threshold_minutes=15,
        )
        db.add(schedule)
        await db.flush()
    return schedule


async def _payroll_run_to_dict(
    payroll_run_id: int,
    db: AsyncSession,
    include_items: bool = True,
) -> dict:
    payroll_run = await db.scalar(
        select(PayrollRun)
        .options(selectinload(PayrollRun.items).selectinload(PayrollItem.employee))
        .where(PayrollRun.id == payroll_run_id)
    )
    if payroll_run is None:
        raise NotFoundError("Payroll run not found")

    data = {
        "id": payroll_run.id,
        "month": payroll_run.month,
        "year": payroll_run.year,
        "status": payroll_run.status,
        "total_cost": str(payroll_run.total_cost),
        "created_by": payroll_run.created_by,
        "approved_by": payroll_run.approved_by,
        "approved_at": payroll_run.approved_at.isoformat() if payroll_run.approved_at else None,
        "created_at": payroll_run.created_at.isoformat() if payroll_run.created_at else None,
    }
    if include_items:
        data["items"] = [_payroll_item_to_dict(item) for item in payroll_run.items]
    return data


def _payroll_item_to_dict(item: PayrollItem) -> dict:
    return {
        "id": item.id,
        "payroll_run_id": item.payroll_run_id,
        "employee_id": item.employee_id,
        "employee_name": item.employee.name if item.employee else None,
        "base_salary": str(item.base_salary),
        "overtime_hours": str(item.overtime_hours),
        "overtime_pay": str(item.overtime_pay),
        "late_deduction": str(item.late_deduction),
        "unpaid_leave_deduction": str(item.unpaid_leave_deduction),
        "bonus": str(item.bonus),
        "net_pay": str(item.net_pay),
        "working_days": item.working_days,
        "present_days": item.present_days,
        "note": item.note,
    }


def _validate_month_year(month: int, year: int) -> None:
    if month < 1 or month > 12:
        raise ServiceError("Month must be between 1 and 12", status_code=400)
    if year < 2000 or year > 2100:
        raise ServiceError("Year must be between 2000 and 2100", status_code=400)
