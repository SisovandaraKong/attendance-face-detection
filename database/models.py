"""SQLAlchemy models for banking-oriented attendance data."""

from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class TimestampMixin:
    """Shared timestamp columns for mutable entities."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Branch(TimestampMixin, Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Department(TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("branch_id", "code", name="uq_departments_branch_code"),
        UniqueConstraint("branch_id", "name", name="uq_departments_branch_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    full_name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    employment_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    join_date: Mapped[date | None] = mapped_column(Date)
    face_enrollment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NOT_ENROLLED"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Shift(TimestampMixin, Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    grace_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    late_after_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    min_checkout_time: Mapped[time | None] = mapped_column(Time)
    is_overnight: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SystemUser(TimestampMixin, Base):
    __tablename__ = "system_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmployeeShiftAssignment(TimestampMixin, Base):
    __tablename__ = "employee_shift_assignments"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "shift_id", "effective_from", name="uq_employee_shift_effective"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("system_users.id"))


class FaceProfile(Base):
    __tablename__ = "face_profiles"
    __table_args__ = (
        UniqueConstraint("employee_id", "profile_version", name="uq_face_profile_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(40))
    feature_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profile_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EnrollmentSession(Base):
    __tablename__ = "enrollment_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    initiated_by: Mapped[int | None] = mapped_column(ForeignKey("system_users.id"))
    capture_device: Mapped[str | None] = mapped_column(String(80))
    required_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=1050)
    collected_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_status: Mapped[str] = mapped_column(String(20), nullable=False, default="IN_PROGRESS")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class EnrollmentSample(Base):
    __tablename__ = "enrollment_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_session_id: Mapped[int] = mapped_column(
        ForeignKey("enrollment_sessions.id"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    file_uri: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    zone_label: Mapped[str] = mapped_column(String(30), nullable=False)
    augmentation_type: Mapped[str | None] = mapped_column(String(30))
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    is_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(200))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KioskDevice(TimestampMixin, Base):
    __tablename__ = "kiosk_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    device_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    device_name: Mapped[str] = mapped_column(String(80), nullable=False)
    location_label: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecognitionEvent(Base):
    __tablename__ = "recognition_events"
    __table_args__ = (
        Index("ix_recognition_events_occurred_at", "occurred_at"),
        Index("ix_recognition_events_employee_occurred", "employee_id", "occurred_at"),
        Index("ix_recognition_events_kiosk_occurred", "kiosk_device_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    kiosk_device_id: Mapped[int | None] = mapped_column(ForeignKey("kiosk_devices.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    face_profile_id: Mapped[int | None] = mapped_column(ForeignKey("face_profiles.id"))
    predicted_label: Mapped[str | None] = mapped_column(String(180))
    confidence: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    liveness_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    event_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="CHECK_IN")
    match_result: Mapped[str] = mapped_column(String(30), nullable=False, default="MATCHED")
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    image_uri: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)
    is_consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AttendanceRecordModel(TimestampMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_attendance_employee_work_date"),
        Index("ix_attendance_work_date_branch", "work_date", "branch_id"),
        Index("ix_attendance_work_date_department", "work_date", "department_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"))
    check_in_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_in_event_id: Mapped[int | None] = mapped_column(ForeignKey("recognition_events.id"))
    check_out_event_id: Mapped[int | None] = mapped_column(ForeignKey("recognition_events.id"))
    attendance_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PRESENT")
    minutes_late: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="AUTO")
    record_state: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("system_users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class AttendanceAdjustment(Base):
    __tablename__ = "attendance_adjustments"
    __table_args__ = (
        Index(
            "ix_attendance_adjustments_record_status",
            "attendance_record_id",
            "approval_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attendance_record_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_records.id"), nullable=False
    )
    requested_by: Mapped[int] = mapped_column(ForeignKey("system_users.id"), nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("system_users.id"))
    adjustment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    old_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    new_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_time", "actor_user_id", "occurred_at"),
        Index("ix_audit_logs_entity_time", "entity_type", "entity_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("system_users.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(36))
    old_values: Mapped[dict | None] = mapped_column(JSON)
    new_values: Mapped[dict | None] = mapped_column(JSON)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)
