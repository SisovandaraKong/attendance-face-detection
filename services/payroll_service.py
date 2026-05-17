"""Service layer for payroll configuration, generation, approval, and reporting."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from database.models import (
    AttendanceRecordModel,
    Branch,
    DeductionRule,
    Department,
    Employee,
    PayrollRecord,
    SalaryConfig,
    SystemUser,
)
from schemas.payroll import (
    PayrollEmployeeInfo,
    PayrollRecordResponse,
    PayrollSummaryBreakdownItem,
    PayrollSummaryResponse,
)

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")
PRESENT_STATUSES = {"PRESENT", "LATE", "CHECKED_OUT"}
PAYROLL_STATUSES = {"DRAFT", "APPROVED", "PAID"}
DEDUCTION_RULE_TYPES = {"PERCENTAGE", "FIXED", "PER_MINUTE"}
SALARY_GRADES = {"TELLER", "OFFICER", "MANAGER", "SUPERVISOR"}


def _decimal(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal | float | int | None) -> Decimal:
    return _decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _money_float(value: Decimal | float | int | None) -> float:
    return float(_money(value))


def _month_bounds(period_year: int, period_month: int) -> tuple[date, date]:
    period_start = date(period_year, period_month, 1)
    if period_month == 12:
        next_month = date(period_year + 1, 1, 1)
    else:
        next_month = date(period_year, period_month + 1, 1)
    return period_start, next_month


def _count_weekdays(start_date: date, end_date: date) -> int:
    if end_date < start_date:
        return 0

    total = 0
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            total += 1
        cursor += timedelta(days=1)
    return total


class PayrollService:
    """Business logic for payroll configuration and monthly payroll processing."""

    @staticmethod
    def _normalize_grade(grade: str) -> str:
        normalized = grade.strip().upper()
        if normalized not in SALARY_GRADES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid grade. Allowed values: {', '.join(sorted(SALARY_GRADES))}",
            )
        return normalized

    @staticmethod
    def _normalize_rule_type(rule_type: str) -> str:
        normalized = rule_type.strip().upper()
        if normalized not in DEDUCTION_RULE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid rule type. Allowed values: {', '.join(sorted(DEDUCTION_RULE_TYPES))}",
            )
        return normalized

    @staticmethod
    def _normalize_status(status_value: str) -> str:
        normalized = status_value.strip().upper()
        if normalized not in PAYROLL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payroll status. Allowed values: {', '.join(sorted(PAYROLL_STATUSES))}",
            )
        return normalized

    @staticmethod
    def _attendance_metrics(records: Iterable[AttendanceRecordModel], working_days: int) -> dict[str, int]:
        unique_present_days: set[date] = set()
        days_late = 0
        total_late_minutes = 0
        total_overtime_minutes = 0

        for record in records:
            status_value = (record.attendance_status or "").upper()
            if status_value in PRESENT_STATUSES:
                unique_present_days.add(record.work_date)
            if status_value == "LATE":
                days_late += 1

            total_late_minutes += int(record.minutes_late or 0)
            total_overtime_minutes += int(record.overtime_minutes or 0)

        days_present = len(unique_present_days)
        days_absent = max(working_days - days_present, 0)

        return {
            "days_present": days_present,
            "days_absent": days_absent,
            "days_late": days_late,
            "total_late_minutes": total_late_minutes,
            "total_overtime_minutes": total_overtime_minutes,
        }

    @staticmethod
    def _get_active_salary_config(
        employee_id: int,
        period_end: date,
        db: Session,
    ) -> SalaryConfig:
        statement = (
            select(SalaryConfig)
            .where(
                SalaryConfig.employee_id == employee_id,
                SalaryConfig.is_active.is_(True),
                SalaryConfig.effective_from <= period_end,
            )
            .order_by(SalaryConfig.effective_from.desc(), SalaryConfig.id.desc())
        )
        config = db.scalar(statement)
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active salary config found for employee_id={employee_id}",
            )
        return config

    @staticmethod
    def _get_applicable_deduction_rules(grade: str, db: Session) -> list[DeductionRule]:
        statement = (
            select(DeductionRule)
            .where(
                DeductionRule.is_active.is_(True),
                or_(
                    DeductionRule.applies_to_grade.is_(None),
                    DeductionRule.applies_to_grade == grade,
                ),
            )
            .order_by(DeductionRule.name.asc())
        )
        return list(db.scalars(statement).all())

    @staticmethod
    def _build_record_response(
        record: PayrollRecord,
        employee: Employee,
        branch: Branch | None = None,
        department: Department | None = None,
    ) -> PayrollRecordResponse:
        deductions_json = {
            key: _money_float(value)
            for key, value in (record.deductions_json or {}).items()
        }
        return PayrollRecordResponse(
            id=record.id,
            employee_id=record.employee_id,
            period_month=record.period_month,
            period_year=record.period_year,
            working_days_in_period=record.working_days_in_period,
            days_present=record.days_present,
            days_absent=record.days_absent,
            days_late=record.days_late,
            total_late_minutes=record.total_late_minutes,
            total_overtime_minutes=record.total_overtime_minutes,
            base_salary=_money_float(record.base_salary),
            transport_allowance=_money_float(record.transport_allowance),
            meal_allowance=_money_float(record.meal_allowance),
            overtime_pay=_money_float(record.overtime_pay),
            gross_pay=_money_float(record.gross_pay),
            deductions_json=deductions_json,
            total_deductions=_money_float(record.total_deductions),
            net_pay=_money_float(record.net_pay),
            status=record.status,
            approved_by=record.approved_by,
            approved_at=record.approved_at,
            generated_at=record.generated_at,
            employee=PayrollEmployeeInfo(
                id=employee.id,
                employee_code=employee.employee_code,
                full_name=employee.full_name,
                branch_name=branch.name if branch else None,
                department_name=department.name if department else None,
            ),
        )

    def run_payroll(
        self,
        period_month: int,
        period_year: int,
        db: Session,
        employee_ids: list[int] | None = None,
    ) -> list[PayrollRecord]:
        """Generate or refresh draft payroll records for a month/year period."""
        if period_month < 1 or period_month > 12:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period_month must be 1-12")

        period_start, next_month = _month_bounds(period_year, period_month)
        period_end = next_month - timedelta(days=1)

        statement = select(Employee).where(
            Employee.is_active.is_(True),
            Employee.employment_status == "ACTIVE",
            or_(Employee.join_date.is_(None), Employee.join_date <= period_end),
        )
        if employee_ids:
            statement = statement.where(Employee.id.in_(employee_ids))
        employees = list(db.scalars(statement.order_by(Employee.full_name.asc())).all())

        if employee_ids and len(employees) != len(set(employee_ids)):
            found_ids = {employee.id for employee in employees}
            missing_ids = sorted(set(employee_ids) - found_ids)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee not found or inactive: {missing_ids}",
            )
        if not employees:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active employees found for payroll run",
            )

        updated_records: list[PayrollRecord] = []
        for employee in employees:
            active_start = max(period_start, employee.join_date or period_start)
            working_days = _count_weekdays(active_start, period_end)

            attendance_records = list(
                db.scalars(
                    select(AttendanceRecordModel)
                    .where(
                        AttendanceRecordModel.employee_id == employee.id,
                        AttendanceRecordModel.work_date >= period_start,
                        AttendanceRecordModel.work_date < next_month,
                    )
                    .order_by(AttendanceRecordModel.work_date.asc())
                ).all()
            )

            metrics = self._attendance_metrics(attendance_records, working_days)
            salary_config = self._get_active_salary_config(employee.id, period_end, db)

            base_salary = _money(salary_config.base_salary)
            transport_allowance = _money(salary_config.transport_allowance)
            meal_allowance = _money(salary_config.meal_allowance)
            overtime_multiplier = _decimal(salary_config.overtime_rate_multiplier)

            if working_days == 0:
                overtime_pay = ZERO
            else:
                hourly_rate = base_salary / Decimal(working_days) / Decimal("8")
                overtime_hours = Decimal(metrics["total_overtime_minutes"]) / Decimal("60")
                overtime_pay = _money(hourly_rate * overtime_hours * overtime_multiplier)

            gross_pay = _money(base_salary + transport_allowance + meal_allowance + overtime_pay)

            deductions: dict[str, float] = {}
            total_deductions = ZERO
            for rule in self._get_applicable_deduction_rules(salary_config.grade, db):
                rule_type = self._normalize_rule_type(rule.rule_type)
                if rule_type == "PERCENTAGE":
                    amount = gross_pay * (_decimal(rule.value) / Decimal("100"))
                elif rule_type == "FIXED":
                    amount = _decimal(rule.value)
                else:
                    amount = Decimal(metrics["total_late_minutes"]) * _decimal(rule.value)

                rounded_amount = _money(amount)
                deductions[rule.name] = float(rounded_amount)
                total_deductions += rounded_amount

            total_deductions = _money(total_deductions)
            net_pay = _money(gross_pay - total_deductions)

            existing = db.scalar(
                select(PayrollRecord).where(
                    PayrollRecord.employee_id == employee.id,
                    PayrollRecord.period_month == period_month,
                    PayrollRecord.period_year == period_year,
                )
            )
            if existing is not None and existing.status in {"APPROVED", "PAID"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Payroll for employee_id={employee.id} period "
                        f"{period_month}/{period_year} is already {existing.status}"
                    ),
                )

            record = existing or PayrollRecord(
                employee_id=employee.id,
                period_month=period_month,
                period_year=period_year,
            )
            if existing is None:
                db.add(record)

            record.working_days_in_period = working_days
            record.days_present = metrics["days_present"]
            record.days_absent = metrics["days_absent"]
            record.days_late = metrics["days_late"]
            record.total_late_minutes = metrics["total_late_minutes"]
            record.total_overtime_minutes = metrics["total_overtime_minutes"]
            record.base_salary = base_salary
            record.transport_allowance = transport_allowance
            record.meal_allowance = meal_allowance
            record.overtime_pay = overtime_pay
            record.gross_pay = gross_pay
            record.deductions_json = deductions
            record.total_deductions = total_deductions
            record.net_pay = net_pay
            record.status = "DRAFT"
            record.approved_by = None
            record.approved_at = None
            record.generated_at = datetime.now(timezone.utc)
            db.flush()
            updated_records.append(record)

        return updated_records

    def approve_payroll(
        self,
        record_id: int,
        approved_by_user_id: int,
        db: Session,
    ) -> PayrollRecord:
        """Approve a draft payroll record and capture approver metadata."""
        record = db.get(PayrollRecord, record_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll record not found")

        approver = db.get(SystemUser, approved_by_user_id)
        if approver is None or not approver.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approving user not found")

        if record.status == "PAID":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Paid payroll cannot be re-approved")
        if record.status == "APPROVED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payroll record is already approved")

        record.status = "APPROVED"
        record.approved_by = approved_by_user_id
        record.approved_at = datetime.now(timezone.utc)
        db.flush()
        return record

    def get_payroll_records(
        self,
        period_month: int,
        period_year: int,
        db: Session,
        status_value: str | None = None,
    ) -> list[PayrollRecordResponse]:
        """Return payroll records for a period with optional status filtering."""
        statement = (
            select(PayrollRecord, Employee, Branch, Department)
            .join(Employee, Employee.id == PayrollRecord.employee_id)
            .join(Branch, Branch.id == Employee.branch_id)
            .join(Department, Department.id == Employee.department_id)
            .where(
                PayrollRecord.period_month == period_month,
                PayrollRecord.period_year == period_year,
            )
            .order_by(Employee.full_name.asc())
        )
        if status_value:
            normalized_status = self._normalize_status(status_value)
            statement = statement.where(PayrollRecord.status == normalized_status)

        rows = db.execute(statement).all()
        return [
            self._build_record_response(record, employee, branch, department)
            for record, employee, branch, department in rows
        ]

    def get_payroll_record(self, record_id: int, db: Session) -> PayrollRecordResponse:
        """Return a single payroll record with employee, branch, and department context."""
        row = db.execute(
            select(PayrollRecord, Employee, Branch, Department)
            .join(Employee, Employee.id == PayrollRecord.employee_id)
            .join(Branch, Branch.id == Employee.branch_id)
            .join(Department, Department.id == Employee.department_id)
            .where(PayrollRecord.id == record_id)
        ).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll record not found")

        record, employee, branch, department = row
        return self._build_record_response(record, employee, branch, department)

    def get_payroll_summary(
        self,
        period_month: int,
        period_year: int,
        db: Session,
    ) -> PayrollSummaryResponse:
        """Aggregate payroll totals by branch and department for a monthly report."""
        rows = db.execute(
            select(
                Branch.id,
                Branch.name,
                Department.id,
                Department.name,
                func.count(PayrollRecord.id),
                func.coalesce(func.sum(PayrollRecord.gross_pay), 0),
                func.coalesce(func.sum(PayrollRecord.total_deductions), 0),
                func.coalesce(func.sum(PayrollRecord.net_pay), 0),
            )
            .join(Employee, Employee.branch_id == Branch.id)
            .join(Department, Department.id == Employee.department_id)
            .join(PayrollRecord, PayrollRecord.employee_id == Employee.id)
            .where(
                PayrollRecord.period_month == period_month,
                PayrollRecord.period_year == period_year,
            )
            .group_by(Branch.id, Branch.name, Department.id, Department.name)
            .order_by(Branch.name.asc(), Department.name.asc())
        ).all()

        breakdown: list[PayrollSummaryBreakdownItem] = []
        total_employees = 0
        total_gross = ZERO
        total_deductions = ZERO
        total_net = ZERO

        for branch_id, branch_name, department_id, department_name, employee_count, gross, deductions, net in rows:
            total_employees += int(employee_count or 0)
            total_gross += _money(gross)
            total_deductions += _money(deductions)
            total_net += _money(net)
            breakdown.append(
                PayrollSummaryBreakdownItem(
                    branch_id=branch_id,
                    branch_name=branch_name,
                    department_id=department_id,
                    department_name=department_name,
                    total_employees=int(employee_count or 0),
                    total_gross=_money_float(gross),
                    total_deductions=_money_float(deductions),
                    total_net=_money_float(net),
                )
            )

        return PayrollSummaryResponse(
            total_employees=total_employees,
            total_gross=_money_float(total_gross),
            total_deductions=_money_float(total_deductions),
            total_net=_money_float(total_net),
            breakdown=breakdown,
        )

    def list_salary_configs(self, db: Session) -> list[SalaryConfig]:
        """List salary configurations ordered by employee and effective date."""
        return list(
            db.scalars(
                select(SalaryConfig)
                .order_by(SalaryConfig.employee_id.asc(), SalaryConfig.effective_from.desc())
            ).all()
        )

    def create_salary_config(
        self,
        *,
        employee_id: int,
        effective_from: date,
        base_salary: float,
        overtime_rate_multiplier: float,
        transport_allowance: float,
        meal_allowance: float,
        grade: str,
        is_active: bool,
        db: Session,
    ) -> SalaryConfig:
        """Create a salary configuration and retire older active configs for the employee."""
        employee = db.get(Employee, employee_id)
        if employee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        normalized_grade = self._normalize_grade(grade)
        if is_active:
            existing_active = db.scalars(
                select(SalaryConfig).where(
                    SalaryConfig.employee_id == employee_id,
                    SalaryConfig.is_active.is_(True),
                )
            ).all()
            for row in existing_active:
                row.is_active = False

        config = SalaryConfig(
            employee_id=employee_id,
            effective_from=effective_from,
            base_salary=_money(base_salary),
            overtime_rate_multiplier=_money(overtime_rate_multiplier),
            transport_allowance=_money(transport_allowance),
            meal_allowance=_money(meal_allowance),
            grade=normalized_grade,
            is_active=is_active,
        )
        db.add(config)
        db.flush()
        return config

    def list_deduction_rules(self, db: Session) -> list[DeductionRule]:
        """List all deduction rules ordered by active flag and name."""
        return list(
            db.scalars(
                select(DeductionRule)
                .order_by(DeductionRule.is_active.desc(), DeductionRule.name.asc())
            ).all()
        )

    def create_deduction_rule(
        self,
        *,
        name: str,
        rule_type: str,
        value: float,
        applies_to_grade: str | None,
        is_active: bool,
        db: Session,
    ) -> DeductionRule:
        """Create a deduction rule with optional grade scoping."""
        normalized_rule_type = self._normalize_rule_type(rule_type)
        normalized_grade = None
        if applies_to_grade:
            normalized_grade = self._normalize_grade(applies_to_grade)

        rule = DeductionRule(
            name=name.strip(),
            rule_type=normalized_rule_type,
            value=_money(value),
            applies_to_grade=normalized_grade,
            is_active=is_active,
        )
        db.add(rule)
        db.flush()
        return rule

    def toggle_deduction_rule(self, rule_id: int, is_active: bool, db: Session) -> DeductionRule:
        """Toggle a deduction rule active state."""
        rule = db.get(DeductionRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deduction rule not found")
        rule.is_active = is_active
        db.flush()
        return rule


payroll_service = PayrollService()
