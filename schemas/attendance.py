"""
schemas/attendance.py
─────────────────────────────────────────────────────────────
Pydantic models for all request / response payloads.

Every API response follows the same envelope:
  { "success": bool, "data": ..., "message": str }
─────────────────────────────────────────────────────────────
"""

from typing import Any, List

from pydantic import BaseModel, Field


# ── Generic response envelope ────────────────────────────────
class APIResponse(BaseModel):
    success: bool
    data: Any = None
    message: str = ""


# ── Attendance record ────────────────────────────────────────
class AttendanceRecord(BaseModel):
    name: str
    date: str          # "YYYY-MM-DD"
    time: str          # "HH:MM:SS"
    status: str = "Present"


class AttendanceListResponse(APIResponse):
    data: List[AttendanceRecord] = []


class AttendanceAdminRecord(BaseModel):
    employee_code: str
    employee_name: str
    branch: str
    department: str
    work_date: str
    check_in_time: str | None = None
    check_out_time: str | None = None
    attendance_status: str
    minutes_late: int = 0
    overtime_minutes: int = 0
    source_type: str
    record_state: str
    check_in_outcome: str | None = None
    check_out_outcome: str | None = None


class AttendanceAdminListResponse(APIResponse):
    data: List[AttendanceAdminRecord] = []


class RecognitionEventInfo(BaseModel):
    id: int
    occurred_at: str
    employee_name: str | None = None
    employee_code: str | None = None
    predicted_label: str | None = None
    confidence: float
    liveness_score: float | None = None
    event_mode: str
    match_result: str
    business_outcome: str | None = None
    attendance_action: str | None = None
    duplicate_suppressed: bool = False
    snapshot_reference: str | None = None
    branch: str | None = None
    kiosk_device: str | None = None
    source: str | None = None


class RecognitionEventListResponse(APIResponse):
    data: List[RecognitionEventInfo] = []


class RecognitionEventStats(BaseModel):
    total_events: int
    matched_events: int
    unregistered_events: int
    unknown_events: int
    review_required_events: int
    duplicate_ignored_events: int = 0
    outside_shift_window_events: int = 0
    rejected_events: int = 0


class ReportSummary(BaseModel):
    total_employees: int
    enrolled_employees: int
    attendance_records_today: int
    open_attendance_records: int
    matched_recognition_today: int
    unregistered_recognition_today: int
    present_records: int = 0
    late_records: int = 0
    checked_out_records: int = 0
    review_required_records: int = 0
    duplicate_ignored_events: int = 0
    outside_shift_events: int = 0
    unrecognized_events: int = 0
    branch_breakdown: dict[str, int]


# ── Person management ────────────────────────────────────────
class PersonInfo(BaseModel):
    id: int
    employee_code: str
    full_name: str
    branch_name: str
    department_name: str
    employment_status: str
    enrollment_status: str
    dataset_key: str                    # directory-friendly name
    image_count: int
    complete: bool
    is_active: bool


class PersonListResponse(APIResponse):
    data: List[PersonInfo] = []


class EmployeeCreateRequest(BaseModel):
    employee_code: str = Field(min_length=1, max_length=30)
    full_name: str = Field(min_length=1, max_length=180)
    email: str | None = Field(default=None, max_length=120)


class EmployeeUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=180)
    email: str | None = Field(default=None, max_length=120)
    employment_status: str | None = Field(default=None, max_length=20)
    face_enrollment_status: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class BranchInfo(BaseModel):
    id: int
    code: str
    name: str
    city: str | None = None
    is_active: bool


class ShiftInfo(BaseModel):
    id: int
    code: str
    name: str
    start_time: str
    end_time: str
    grace_minutes: int
    late_after_minutes: int
    is_active: bool


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    full_name: str


class SystemHealth(BaseModel):
    app_status: str
    database_status: str
    model_ready: bool
    known_persons_count: int
    today_recognition_events: int
    today_attendance_records: int


# ── Prediction result (used internally + exposed to JS) ──────
class PredictionResult(BaseModel):
    label: str            # "Unknown" or person name (spaces)
    confidence: float     # 0.0 – 1.0
    recognised: bool      # True when confidence ≥ threshold
