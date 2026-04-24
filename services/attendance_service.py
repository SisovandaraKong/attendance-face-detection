"""Database-first attendance service with optional CSV export utilities."""

import csv
import os
from io import StringIO
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from sqlalchemy import Date, and_, cast, func, or_, select
from sqlalchemy.orm import aliased

from database.models import (
    AttendanceRecordModel,
    Branch,
    Department,
    Employee,
    EmployeeShiftAssignment,
    KioskDevice,
    RecognitionEvent,
    Shift,
)
from database.session import get_db_session
from schemas.attendance import (
    AttendanceAdminRecord,
    AttendanceRecord,
    BranchInfo,
    RecognitionEventInfo,
    RecognitionEventStats,
    ReportSummary,
    ShiftInfo,
    SystemHealth,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
BUSINESS_DUPLICATE_WINDOW_SECONDS = max(
    int(os.getenv("RECOGNITION_COOLDOWN", "120")),
    120,
)
CHECKIN_WINDOW_BEFORE_SHIFT_MINUTES = int(os.getenv("CHECKIN_WINDOW_BEFORE_SHIFT_MINUTES", "90"))
CHECKIN_WINDOW_AFTER_SHIFT_MINUTES = int(os.getenv("CHECKIN_WINDOW_AFTER_SHIFT_MINUTES", "180"))
CHECKOUT_WINDOW_BEFORE_SHIFT_MINUTES = int(os.getenv("CHECKOUT_WINDOW_BEFORE_SHIFT_MINUTES", "60"))
CHECKOUT_WINDOW_AFTER_SHIFT_MINUTES = int(os.getenv("CHECKOUT_WINDOW_AFTER_SHIFT_MINUTES", "240"))
DEFAULT_MIN_CHECKOUT_BEFORE_END_MINUTES = int(os.getenv("MIN_CHECKOUT_BEFORE_END_MINUTES", "30"))

ATTENDANCE_STATUS_PRESENT = "PRESENT"
ATTENDANCE_STATUS_LATE = "LATE"
ATTENDANCE_STATUS_CHECKED_OUT = "CHECKED_OUT"
ATTENDANCE_STATUS_MISSING_CHECKIN = "MISSING_CHECKIN"

EVENT_OUTCOME_ATTENDANCE_ACCEPTED = "ATTENDANCE_ACCEPTED"
EVENT_OUTCOME_DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
EVENT_OUTCOME_OUTSIDE_SHIFT = "OUTSIDE_SHIFT"
EVENT_OUTCOME_UNRECOGNIZED = "UNRECOGNIZED"


def _log_path(date_str: str) -> str:
    return os.path.join(LOGS_DIR, f"attendance_{date_str}.csv")


def _ensure_baseline_entities(session) -> tuple[Branch, Department, Shift, KioskDevice]:
    branch = session.scalar(select(Branch).where(Branch.code == "HQ"))
    if branch is None:
        branch = Branch(code="HQ", name="Headquarters", city="Phnom Penh", is_active=True)
        session.add(branch)
        session.flush()

    department = session.scalar(
        select(Department).where(
            and_(Department.branch_id == branch.id, Department.code == "OPS")
        )
    )
    if department is None:
        department = Department(
            branch_id=branch.id,
            code="OPS",
            name="Operations",
            is_active=True,
        )
        session.add(department)
        session.flush()

    shift = session.scalar(select(Shift).where(Shift.code == "GENERAL"))
    if shift is None:
        shift = Shift(
            code="GENERAL",
            name="Bank Office Shift",
            start_time=time(hour=8, minute=0),
            end_time=time(hour=17, minute=0),
            grace_minutes=10,
            late_after_minutes=10,
            min_checkout_time=time(hour=16, minute=30),
            is_overnight=False,
            is_active=True,
        )
        session.add(shift)
        session.flush()

    device = session.scalar(select(KioskDevice).where(KioskDevice.device_code == "KIOSK-01"))
    if device is None:
        device = KioskDevice(
            branch_id=branch.id,
            device_code="KIOSK-01",
            device_name="Main Lobby Kiosk",
            location_label="Main Entrance",
            is_active=True,
        )
        session.add(device)
        session.flush()

    return branch, department, shift, device


def _dataset_key(name: str) -> str:
    return "_".join(name.strip().split())


def _parse_mode(event_mode: str) -> tuple[str, str]:
    mode = (event_mode or "check-in").strip().lower()
    if mode == "check-out":
        return "CHECK_OUT", "Check Out"
    return "CHECK_IN", "Check In"


def _get_shift_bounds(shift: Shift, work_date: date) -> tuple[datetime, datetime]:
    shift_start = datetime.combine(work_date, shift.start_time)
    shift_end = datetime.combine(work_date, shift.end_time)
    if shift.is_overnight and shift_end <= shift_start:
        shift_end = shift_end + timedelta(days=1)
    return shift_start, shift_end


def _get_min_checkout_time(shift: Shift, work_date: date) -> datetime:
    if shift.min_checkout_time:
        min_checkout = datetime.combine(work_date, shift.min_checkout_time)
    else:
        _, shift_end = _get_shift_bounds(shift, work_date)
        min_checkout = shift_end - timedelta(minutes=DEFAULT_MIN_CHECKOUT_BEFORE_END_MINUTES)
    shift_start, shift_end = _get_shift_bounds(shift, work_date)
    if shift.is_overnight and min_checkout < shift_start:
        min_checkout = min_checkout + timedelta(days=1)
    if min_checkout > shift_end:
        return shift_end
    return min_checkout


def _get_checkin_window(shift: Shift, work_date: date) -> tuple[datetime, datetime]:
    shift_start, _ = _get_shift_bounds(shift, work_date)
    return (
        shift_start - timedelta(minutes=CHECKIN_WINDOW_BEFORE_SHIFT_MINUTES),
        shift_start + timedelta(minutes=CHECKIN_WINDOW_AFTER_SHIFT_MINUTES),
    )


def _get_checkout_window(shift: Shift, work_date: date) -> tuple[datetime, datetime]:
    _, shift_end = _get_shift_bounds(shift, work_date)
    min_checkout = _get_min_checkout_time(shift, work_date)
    return (
        min_checkout - timedelta(minutes=CHECKOUT_WINDOW_BEFORE_SHIFT_MINUTES),
        shift_end + timedelta(minutes=CHECKOUT_WINDOW_AFTER_SHIFT_MINUTES),
    )


def _build_event_metadata(
    *,
    source: str = "face_service",
    snapshot_reference: str | None = None,
    liveness_result: str | None = None,
    duplicate_window_seconds: int = BUSINESS_DUPLICATE_WINDOW_SECONDS,
) -> dict:
    metadata = {
        "source": source,
        "duplicate_window_seconds": duplicate_window_seconds,
    }
    if snapshot_reference:
        metadata["snapshot_reference"] = snapshot_reference
    if liveness_result:
        metadata["liveness_result"] = liveness_result
    return metadata


def _update_event_business_outcome(
    event: RecognitionEvent,
    *,
    outcome: str,
    action: str,
    duplicate_suppressed: bool = False,
    reason: str | None = None,
) -> None:
    metadata = dict(event.metadata_json or {})
    metadata["business_outcome"] = outcome
    metadata["attendance_action"] = action
    metadata["duplicate_suppressed"] = duplicate_suppressed
    if reason:
        metadata["reason"] = reason
    event.metadata_json = metadata


def _find_recent_duplicate_event(
    session,
    employee_id: int,
    mode_code: str,
    occurred_at: datetime,
) -> RecognitionEvent | None:
    boundary = occurred_at - timedelta(seconds=BUSINESS_DUPLICATE_WINDOW_SECONDS)
    return session.scalar(
        select(RecognitionEvent)
        .where(
            RecognitionEvent.employee_id == employee_id,
            RecognitionEvent.event_mode == mode_code,
            RecognitionEvent.occurred_at >= boundary,
            RecognitionEvent.occurred_at < occurred_at,
        )
        .order_by(RecognitionEvent.occurred_at.desc())
    )


def _is_within_shift_window(shift: Shift, event: RecognitionEvent) -> tuple[bool, str | None]:
    work_date = event.occurred_at.date()

    if event.event_mode == "CHECK_IN":
        earliest, latest = _get_checkin_window(shift, work_date)
        if event.occurred_at < earliest or event.occurred_at > latest:
            return False, "outside_checkin_window"
        return True, None

    earliest, latest = _get_checkout_window(shift, work_date)
    if event.occurred_at < earliest or event.occurred_at > latest:
        return False, "outside_checkout_window"
    min_checkout = _get_min_checkout_time(shift, work_date)
    if event.occurred_at < min_checkout:
        return False, "before_min_checkout_time"
    return True, None


def _find_employee_by_name(session, display_name: str) -> Employee | None:
    return session.scalar(
        select(Employee).where(func.lower(Employee.full_name) == display_name.lower())
    )


def _get_employee_shift(session, employee: Employee, work_date: date, fallback_shift: Shift) -> Shift:
    assignment = session.execute(
        select(Shift)
        .join(EmployeeShiftAssignment, EmployeeShiftAssignment.shift_id == Shift.id)
        .where(
            EmployeeShiftAssignment.employee_id == employee.id,
            EmployeeShiftAssignment.effective_from <= work_date,
            or_(
                EmployeeShiftAssignment.effective_to.is_(None),
                EmployeeShiftAssignment.effective_to >= work_date,
            ),
        )
        .order_by(EmployeeShiftAssignment.effective_from.desc())
    ).scalars().first()
    return assignment or fallback_shift


def _get_attendance_record(session, employee_id: int, work_date: date) -> AttendanceRecordModel | None:
    return session.scalar(
        select(AttendanceRecordModel).where(
            and_(
                AttendanceRecordModel.employee_id == employee_id,
                AttendanceRecordModel.work_date == work_date,
            )
        )
    )


def _is_duplicate_for_existing_record(
    row: AttendanceRecordModel | None,
    event: RecognitionEvent,
) -> tuple[bool, str | None]:
    if row is None:
        return False, None

    if event.event_mode == "CHECK_IN" and row.check_in_time is not None:
        return True, "already_checked_in"
    if event.event_mode == "CHECK_OUT" and row.check_out_time is not None:
        return True, "already_checked_out"
    return False, None


def _upsert_attendance_record(
    session,
    employee: Employee,
    shift: Shift,
    event: RecognitionEvent,
) -> str:
    work_date = event.occurred_at.date()
    row = _get_attendance_record(session, employee.id, work_date)
    created = row is None

    if row is None:
        row = AttendanceRecordModel(
            employee_id=employee.id,
            branch_id=employee.branch_id,
            department_id=employee.department_id,
            work_date=work_date,
            shift_id=shift.id,
            attendance_status="PRESENT",
            source_type="AUTO",
            record_state="OPEN",
        )
        session.add(row)
        session.flush()

    shift_start, shift_end = _get_shift_bounds(shift, work_date)
    min_checkout = _get_min_checkout_time(shift, work_date)

    if event.event_mode == "CHECK_OUT":
        row.check_out_time = event.occurred_at
        row.check_out_event_id = event.id
        row.attendance_status = ATTENDANCE_STATUS_CHECKED_OUT
        if row.check_in_time is None:
            row.record_state = "REVIEW_REQUIRED"
            row.notes = "Checkout captured without a prior check-in."
        elif event.occurred_at < row.check_in_time:
            row.record_state = "REVIEW_REQUIRED"
            row.notes = "Checkout occurred before the recorded check-in time."
        elif event.occurred_at < min_checkout:
            row.record_state = "REVIEW_REQUIRED"
            row.notes = "Checkout captured before the bank minimum checkout time."
        else:
            row.record_state = "CLOSED"

        if event.occurred_at > shift_end:
            row.overtime_minutes = int(
                (event.occurred_at - shift_end).total_seconds() // 60
            )
    else:
        if row.check_in_time is None or event.occurred_at < row.check_in_time:
            row.check_in_time = event.occurred_at
        row.check_in_event_id = event.id
        late_boundary = shift_start + timedelta(minutes=max(shift.grace_minutes, shift.late_after_minutes))
        row.record_state = "OPEN"
        row.notes = None
        if event.occurred_at > late_boundary:
            row.minutes_late = int((event.occurred_at - shift_start).total_seconds() // 60)
            row.attendance_status = ATTENDANCE_STATUS_LATE
        else:
            row.minutes_late = 0
            row.attendance_status = ATTENDANCE_STATUS_PRESENT
    return "CREATED" if created else "UPDATED"


def _record_unregistered_recognition(
    session,
    device: KioskDevice,
    display_name: str,
    confidence: float,
    mode_code: str,
) -> None:
    event = RecognitionEvent(
        occurred_at=datetime.now(),
        kiosk_device_id=device.id,
        employee_id=None,
        predicted_label=display_name,
        confidence=confidence,
        event_mode=mode_code,
        match_result="UNREGISTERED",
        metadata_json={"source": "face_service", "reason": "employee_not_registered"},
    )
    session.add(event)


def _event_to_attendance_record(event: RecognitionEvent) -> AttendanceRecord:
    mode_label = "Check Out" if event.event_mode == "CHECK_OUT" else "Check In"
    return AttendanceRecord(
        name=event.predicted_label or "Unknown",
        date=event.occurred_at.strftime("%Y-%m-%d"),
        time=event.occurred_at.strftime("%H:%M:%S"),
        status=mode_label,
    )


def _read_legacy_csv(date_str: str) -> List[AttendanceRecord]:
    path = _log_path(date_str)
    if not os.path.exists(path):
        return []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            AttendanceRecord(
                name=row.get("Name", ""),
                date=row.get("Date", date_str),
                time=row.get("Time", ""),
                status=row.get("Status", "Present"),
            )
            for row in reader
        ]


def read_log(date_str: Optional[str] = None) -> List[AttendanceRecord]:
    """
    Read public timeline entries from the database.

    Legacy CSV files are only consulted for historical dates that were written
    before the database-first refactor.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    target = datetime.strptime(date_str, "%Y-%m-%d").date()

    with get_db_session() as session:
        events = session.scalars(
            select(RecognitionEvent)
            .where(
                and_(
                    cast(RecognitionEvent.occurred_at, Date) == target,
                    RecognitionEvent.match_result == "MATCHED",
                )
            )
            .order_by(RecognitionEvent.occurred_at.asc())
        ).all()

    if events:
        return [_event_to_attendance_record(event) for event in events]

    return _read_legacy_csv(date_str)


def record_recognition_event(
    name: str,
    event_mode: str = "check-in",
    confidence: float = 1.0,
    liveness_score: float | None = None,
    liveness_passed: bool | None = None,
    liveness_message: str | None = None,
    source_id: str | None = None,
    snapshot_reference: str | None = None,
) -> RecognitionEvent:
    now = datetime.now()
    display_name = name.replace("_", " ").strip()
    mode_code, mode_label = _parse_mode(event_mode)

    with get_db_session() as session:
        branch, department, fallback_shift, device = _ensure_baseline_entities(session)
        employee = _find_employee_by_name(session, display_name)

        event = RecognitionEvent(
            occurred_at=now,
            kiosk_device_id=device.id,
            employee_id=employee.id if employee else None,
            predicted_label=display_name,
            confidence=confidence,
            liveness_score=liveness_score,
            event_mode=mode_code,
            match_result="MATCHED" if employee else "UNREGISTERED",
            metadata_json=_build_event_metadata(
                source=source_id or "face_service",
                snapshot_reference=snapshot_reference,
                liveness_result=(
                    "PASS"
                    if liveness_passed is True
                    else "FAILED"
                    if liveness_passed is False
                    else "UNKNOWN"
                ),
            ),
            image_uri=snapshot_reference,
        )
        session.add(event)
        session.flush()

        if liveness_message:
            metadata = dict(event.metadata_json or {})
            metadata["liveness_message"] = liveness_message
            event.metadata_json = metadata

        if liveness_passed is False:
            event.match_result = "LOW_LIVENESS"
            _update_event_business_outcome(
                event,
                outcome="LIVENESS_FAILED",
                action="NO_ATTENDANCE_RECORD",
                reason=liveness_message or "liveness_not_confirmed",
            )
            return event

        if employee is None:
            _update_event_business_outcome(
                event,
                outcome=EVENT_OUTCOME_UNRECOGNIZED,
                action="NO_ATTENDANCE_RECORD",
                reason="employee_not_registered",
            )
            return event

        active_shift = _get_employee_shift(session, employee, now.date(), fallback_shift)
        existing_record = _get_attendance_record(session, employee.id, now.date())

        duplicate = _find_recent_duplicate_event(session, employee.id, mode_code, now)
        if duplicate is not None:
            event.match_result = "DUPLICATE_IGNORED"
            _update_event_business_outcome(
                event,
                outcome=EVENT_OUTCOME_DUPLICATE_IGNORED,
                action="NO_ATTENDANCE_RECORD",
                duplicate_suppressed=True,
                reason="within_duplicate_window",
            )
            return event

        duplicate_record_event, duplicate_reason = _is_duplicate_for_existing_record(existing_record, event)
        if duplicate_record_event:
            event.match_result = "DUPLICATE_IGNORED"
            _update_event_business_outcome(
                event,
                outcome=EVENT_OUTCOME_DUPLICATE_IGNORED,
                action="NO_ATTENDANCE_RECORD",
                duplicate_suppressed=True,
                reason=duplicate_reason,
            )
            return event

        within_window, shift_reason = _is_within_shift_window(active_shift, event)
        if not within_window:
            event.match_result = "OUTSIDE_SHIFT_WINDOW"
            _update_event_business_outcome(
                event,
                outcome=EVENT_OUTCOME_OUTSIDE_SHIFT,
                action="NO_ATTENDANCE_RECORD",
                reason=shift_reason,
            )
            return event

        action = _upsert_attendance_record(session, employee, active_shift, event)
        _update_event_business_outcome(
            event,
            outcome=EVENT_OUTCOME_ATTENDANCE_ACCEPTED,
            action="CHECKED_OUT" if event.event_mode == "CHECK_OUT" else "CHECKED_IN",
        )
        event.is_consumed = True
        event.consumed_at = now

        return event


def write_record(
    name: str,
    event_mode: str = "check-in",
    confidence: float = 1.0,
    liveness_score: float | None = None,
    liveness_passed: bool | None = None,
    liveness_message: str | None = None,
    source_id: str | None = None,
    snapshot_reference: str | None = None,
) -> AttendanceRecord:
    display_name = name.replace("_", " ").strip()
    _, mode_label = _parse_mode(event_mode)
    event = record_recognition_event(
        name=name,
        event_mode=event_mode,
        confidence=confidence,
        liveness_score=liveness_score,
        liveness_passed=liveness_passed,
        liveness_message=liveness_message,
        source_id=source_id,
        snapshot_reference=snapshot_reference,
    )
    business_outcome = (event.metadata_json or {}).get("business_outcome")

    if business_outcome == EVENT_OUTCOME_ATTENDANCE_ACCEPTED:
        status = mode_label
    elif event.match_result == "DUPLICATE_IGNORED":
        status = "Duplicate Ignored"
    elif event.match_result == "OUTSIDE_SHIFT_WINDOW":
        status = "Outside Shift Window"
    elif event.match_result == "LOW_LIVENESS":
        status = "Liveness Failed"
    elif event.match_result == "UNREGISTERED":
        status = "Unrecognized"
    else:
        status = "Rejected Event"

    return AttendanceRecord(
        name=display_name,
        date=event.occurred_at.strftime("%Y-%m-%d"),
        time=event.occurred_at.strftime("%H:%M:%S"),
        status=status,
    )


def list_attendance_records(date_str: Optional[str] = None) -> List[AttendanceAdminRecord]:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    target = datetime.strptime(date_str, "%Y-%m-%d").date()

    check_in_event = aliased(RecognitionEvent)
    check_out_event = aliased(RecognitionEvent)

    with get_db_session() as session:
        rows = session.execute(
            select(
                AttendanceRecordModel,
                Employee,
                Branch,
                Department,
                check_in_event,
                check_out_event,
            )
            .join(Employee, Employee.id == AttendanceRecordModel.employee_id)
            .join(Branch, Branch.id == AttendanceRecordModel.branch_id)
            .join(Department, Department.id == AttendanceRecordModel.department_id)
            .outerjoin(check_in_event, check_in_event.id == AttendanceRecordModel.check_in_event_id)
            .outerjoin(check_out_event, check_out_event.id == AttendanceRecordModel.check_out_event_id)
            .where(AttendanceRecordModel.work_date == target)
            .order_by(AttendanceRecordModel.check_in_time.asc().nullslast(), Employee.full_name.asc())
        ).all()

    if rows:
        return [
            AttendanceAdminRecord(
                employee_code=employee.employee_code,
                employee_name=employee.full_name,
                branch=branch.name,
                department=department.name,
                work_date=record.work_date.strftime("%Y-%m-%d"),
                check_in_time=(
                    record.check_in_time.astimezone().strftime("%H:%M:%S")
                    if record.check_in_time
                    else None
                ),
                check_out_time=(
                    record.check_out_time.astimezone().strftime("%H:%M:%S")
                    if record.check_out_time
                    else None
                ),
                attendance_status=record.attendance_status,
                minutes_late=record.minutes_late,
                overtime_minutes=record.overtime_minutes,
                source_type=record.source_type,
                record_state=record.record_state,
                check_in_outcome=(
                    ((check_in.metadata_json or {}).get("business_outcome") or check_in.match_result)
                    if check_in
                    else None
                ),
                check_out_outcome=(
                    ((check_out.metadata_json or {}).get("business_outcome") or check_out.match_result)
                    if check_out
                    else None
                ),
            )
            for record, employee, branch, department, check_in, check_out in rows
        ]

    return [
        AttendanceAdminRecord(
            employee_code="LEGACY",
            employee_name=record.name,
            branch="Legacy Log",
            department="-",
            work_date=record.date,
            check_in_time=record.time if record.status == "Check In" else None,
            check_out_time=record.time if record.status == "Check Out" else None,
            attendance_status=record.status.upper().replace(" ", "_"),
            minutes_late=0,
            overtime_minutes=0,
            source_type="CSV",
            record_state="CLOSED",
            check_in_outcome="LEGACY_IMPORT",
            check_out_outcome="LEGACY_IMPORT" if record.status == "Check Out" else None,
        )
        for record in read_log(date_str)
    ]


def list_log_dates() -> List[str]:
    dates: set[str] = set()

    with get_db_session() as session:
        attendance_rows = session.execute(
            select(AttendanceRecordModel.work_date).distinct()
        ).all()
        for work_date, in attendance_rows:
            if work_date is not None:
                dates.add(work_date.strftime("%Y-%m-%d"))

        event_rows = session.execute(
            select(RecognitionEvent.occurred_at).distinct()
        ).all()
        for occurred_at, in event_rows:
            if occurred_at is not None:
                dates.add(occurred_at.date().strftime("%Y-%m-%d"))

    if os.path.isdir(LOGS_DIR):
        csv_dates = [
            f[len("attendance_"):-len(".csv")]
            for f in os.listdir(LOGS_DIR)
            if f.startswith("attendance_") and f.endswith(".csv")
        ]
        dates.update(csv_dates)

    return sorted(dates, reverse=True)


def get_summary() -> Dict[str, int]:
    summary: Dict[str, int] = {}

    with get_db_session() as session:
        rows = session.execute(
            select(AttendanceRecordModel.work_date, func.count(AttendanceRecordModel.id))
            .group_by(AttendanceRecordModel.work_date)
        ).all()
        for d, count in rows:
            if d is not None:
                summary[d.strftime("%Y-%m-%d")] = int(count)

    # Include legacy CSV counts for dates that were never migrated.
    for d in list_log_dates():
        if d not in summary:
            summary[d] = len(_read_legacy_csv(d))

    return dict(sorted(summary.items(), reverse=True))


def get_late_trend(days: int = 7) -> Dict[str, int]:
    cutoff = datetime.now().date() - timedelta(days=max(days - 1, 0))
    trend: Dict[str, int] = {}

    with get_db_session() as session:
        rows = session.execute(
            select(AttendanceRecordModel.work_date, func.count(AttendanceRecordModel.id))
            .where(
                and_(
                    AttendanceRecordModel.work_date >= cutoff,
                    AttendanceRecordModel.attendance_status == ATTENDANCE_STATUS_LATE,
                )
            )
            .group_by(AttendanceRecordModel.work_date)
            .order_by(AttendanceRecordModel.work_date.asc())
        ).all()

    for work_date, count in rows:
        trend[work_date.strftime("%Y-%m-%d")] = int(count)
    return trend


def export_attendance_csv(date_str: Optional[str] = None) -> str:
    """Export the current attendance records into CSV for reporting."""
    records = list_attendance_records(date_str)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Employee Code",
            "Employee Name",
            "Branch",
            "Department",
            "Work Date",
            "Check In",
            "Check Out",
            "Attendance Status",
            "Minutes Late",
            "Overtime Minutes",
            "Source Type",
            "Record State",
        ]
    )
    for record in records:
        writer.writerow(
            [
                record.employee_code,
                record.employee_name,
                record.branch,
                record.department,
                record.work_date,
                record.check_in_time or "",
                record.check_out_time or "",
                record.attendance_status,
                record.minutes_late,
                record.overtime_minutes,
                record.source_type,
                record.record_state,
            ]
        )
    return buffer.getvalue()


def list_recognition_events(
    date_str: Optional[str] = None,
    match_result: Optional[str] = None,
) -> List[RecognitionEventInfo]:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    target = datetime.strptime(date_str, "%Y-%m-%d").date()

    with get_db_session() as session:
        query = (
            select(RecognitionEvent, Employee, KioskDevice, Branch)
            .outerjoin(Employee, Employee.id == RecognitionEvent.employee_id)
            .outerjoin(KioskDevice, KioskDevice.id == RecognitionEvent.kiosk_device_id)
            .outerjoin(Branch, Branch.id == KioskDevice.branch_id)
            .where(cast(RecognitionEvent.occurred_at, Date) == target)
            .order_by(RecognitionEvent.occurred_at.desc())
        )
        if match_result:
            query = query.where(RecognitionEvent.match_result == match_result.upper())

        rows = session.execute(query.limit(100)).all()

    return [
        RecognitionEventInfo(
            id=event.id,
            occurred_at=event.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
            employee_name=employee.full_name if employee else None,
            employee_code=employee.employee_code if employee else None,
            predicted_label=event.predicted_label,
            confidence=float(event.confidence),
            liveness_score=float(event.liveness_score) if event.liveness_score is not None else None,
            event_mode=event.event_mode,
            match_result=event.match_result,
            business_outcome=(event.metadata_json or {}).get("business_outcome"),
            attendance_action=(event.metadata_json or {}).get("attendance_action"),
            duplicate_suppressed=bool((event.metadata_json or {}).get("duplicate_suppressed", False)),
            snapshot_reference=event.image_uri or (event.metadata_json or {}).get("snapshot_reference"),
            branch=branch.name if branch else None,
            kiosk_device=kiosk.device_name if kiosk else None,
            source=(event.metadata_json or {}).get("source"),
        )
        for event, employee, kiosk, branch in rows
    ]


def get_recognition_event_stats(date_str: Optional[str] = None) -> RecognitionEventStats:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    target = datetime.strptime(date_str, "%Y-%m-%d").date()

    with get_db_session() as session:
        events = session.scalars(
            select(RecognitionEvent).where(cast(RecognitionEvent.occurred_at, Date) == target)
        ).all()

    counts: dict[str, int] = {}
    for event in events:
        counts[event.match_result] = counts.get(event.match_result, 0) + 1

    review_required = (
        counts.get("UNREGISTERED", 0)
        + counts.get("LOW_CONFIDENCE", 0)
        + counts.get("OUTSIDE_SHIFT_WINDOW", 0)
        + counts.get("LOW_LIVENESS", 0)
    )
    return RecognitionEventStats(
        total_events=len(events),
        matched_events=counts.get("MATCHED", 0),
        unregistered_events=counts.get("UNREGISTERED", 0),
        unknown_events=counts.get("UNKNOWN", 0),
        review_required_events=review_required,
        duplicate_ignored_events=counts.get("DUPLICATE_IGNORED", 0),
        outside_shift_window_events=counts.get("OUTSIDE_SHIFT_WINDOW", 0),
        rejected_events=(
            counts.get("UNREGISTERED", 0)
            + counts.get("OUTSIDE_SHIFT_WINDOW", 0)
            + counts.get("LOW_LIVENESS", 0)
        ),
    )


def get_report_summary(date_str: Optional[str] = None) -> ReportSummary:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    target = datetime.strptime(date_str, "%Y-%m-%d").date()

    with get_db_session() as session:
        total_employees = session.scalar(select(func.count(Employee.id))) or 0
        enrolled_employees = session.scalar(
            select(func.count(Employee.id)).where(Employee.face_enrollment_status == "ENROLLED")
        ) or 0
        attendance_records_today = session.scalar(
            select(func.count(AttendanceRecordModel.id)).where(AttendanceRecordModel.work_date == target)
        ) or 0
        open_attendance_records = session.scalar(
            select(func.count(AttendanceRecordModel.id)).where(
                and_(
                    AttendanceRecordModel.work_date == target,
                    AttendanceRecordModel.record_state == "OPEN",
                )
            )
        ) or 0
        attendance_status_rows = session.execute(
            select(AttendanceRecordModel.attendance_status, func.count(AttendanceRecordModel.id))
            .where(AttendanceRecordModel.work_date == target)
            .group_by(AttendanceRecordModel.attendance_status)
        ).all()
        review_required_records = session.scalar(
            select(func.count(AttendanceRecordModel.id)).where(
                and_(
                    AttendanceRecordModel.work_date == target,
                    AttendanceRecordModel.record_state == "REVIEW_REQUIRED",
                )
            )
        ) or 0

        event_rows = session.execute(
            select(RecognitionEvent.match_result, func.count(RecognitionEvent.id))
            .where(cast(RecognitionEvent.occurred_at, Date) == target)
            .group_by(RecognitionEvent.match_result)
        ).all()

        branch_rows = session.execute(
            select(Branch.name, func.count(AttendanceRecordModel.id))
            .join(AttendanceRecordModel, AttendanceRecordModel.branch_id == Branch.id)
            .where(AttendanceRecordModel.work_date == target)
            .group_by(Branch.name)
        ).all()

    event_counts = {result: int(count) for result, count in event_rows}
    attendance_status_counts = {status: int(count) for status, count in attendance_status_rows}
    branch_breakdown = {name: int(count) for name, count in branch_rows}
    return ReportSummary(
        total_employees=int(total_employees),
        enrolled_employees=int(enrolled_employees),
        attendance_records_today=int(attendance_records_today),
        open_attendance_records=int(open_attendance_records),
        matched_recognition_today=event_counts.get("MATCHED", 0),
        unregistered_recognition_today=event_counts.get("UNREGISTERED", 0),
        present_records=attendance_status_counts.get(ATTENDANCE_STATUS_PRESENT, 0),
        late_records=attendance_status_counts.get(ATTENDANCE_STATUS_LATE, 0),
        checked_out_records=attendance_status_counts.get(ATTENDANCE_STATUS_CHECKED_OUT, 0),
        review_required_records=int(review_required_records),
        duplicate_ignored_events=event_counts.get("DUPLICATE_IGNORED", 0),
        outside_shift_events=event_counts.get("OUTSIDE_SHIFT_WINDOW", 0),
        unrecognized_events=(
            event_counts.get("UNREGISTERED", 0)
            + event_counts.get("UNKNOWN", 0)
            + event_counts.get("LOW_LIVENESS", 0)
        ),
        branch_breakdown=branch_breakdown,
    )


def list_branches() -> List[BranchInfo]:
    with get_db_session() as session:
        branches = session.scalars(select(Branch).order_by(Branch.name.asc())).all()
    return [
        BranchInfo(
            id=branch.id,
            code=branch.code,
            name=branch.name,
            city=branch.city,
            is_active=branch.is_active,
        )
        for branch in branches
    ]


def list_shifts() -> List[ShiftInfo]:
    with get_db_session() as session:
        shifts = session.scalars(select(Shift).order_by(Shift.start_time.asc())).all()
    return [
        ShiftInfo(
            id=shift.id,
            code=shift.code,
            name=shift.name,
            start_time=shift.start_time.strftime("%H:%M"),
            end_time=shift.end_time.strftime("%H:%M"),
            grace_minutes=shift.grace_minutes,
            late_after_minutes=shift.late_after_minutes,
            is_active=shift.is_active,
        )
        for shift in shifts
    ]


def get_system_health(model_ready: bool, known_persons_count: int) -> SystemHealth:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db_session() as session:
        today_events = session.scalar(
            select(func.count(RecognitionEvent.id)).where(
                cast(RecognitionEvent.occurred_at, Date) == datetime.strptime(today, "%Y-%m-%d").date()
            )
        ) or 0
        today_attendance = session.scalar(
            select(func.count(AttendanceRecordModel.id)).where(
                AttendanceRecordModel.work_date == datetime.strptime(today, "%Y-%m-%d").date()
            )
        ) or 0

    return SystemHealth(
        app_status="OK",
        database_status="OK",
        model_ready=model_ready,
        known_persons_count=known_persons_count,
        today_recognition_events=int(today_events),
        today_attendance_records=int(today_attendance),
    )
