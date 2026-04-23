"""
routes/attendance.py
─────────────────────────────────────────────────────────────
Attendance JSON API endpoints for admin portal.
─────────────────────────────────────────────────────────────
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from schemas.attendance import APIResponse, AttendanceListResponse
from services.attendance_service import list_log_dates, read_log

router = APIRouter(prefix="/api/admin/attendance", tags=["admin-attendance"])


# ── JSON API ─────────────────────────────────────────────────

@router.get("/records", response_model=AttendanceListResponse)
async def api_get_records(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
) -> AttendanceListResponse:
    """Return attendance records for a given date as JSON."""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    try:
        records = read_log(date_str)
        return AttendanceListResponse(
            success=True,
            data=records,
            message=f"{len(records)} record(s) for {date_str}",
        )
    except Exception as exc:
        return AttendanceListResponse(
            success=False,
            data=[],
            message=str(exc),
        )


@router.get("/dates", response_model=APIResponse)
async def api_list_dates() -> APIResponse:
    """Return all dates that have attendance log files."""
    return APIResponse(
        success=True,
        data=list_log_dates(),
        message="Available log dates",
    )
