"""
routes/attendance.py
─────────────────────────────────────────────────────────────
Attendance JSON API endpoints for admin portal.
─────────────────────────────────────────────────────────────
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from dependencies.auth import require_roles
from schemas.attendance import APIResponse, AttendanceAdminListResponse
from services.attendance_service import export_attendance_csv, list_attendance_records, list_log_dates

router = APIRouter(
    prefix="/api/admin/attendance",
    tags=["admin-attendance"],
    dependencies=[Depends(require_roles("super_admin", "hr_admin"))],
)


# ── JSON API ─────────────────────────────────────────────────

@router.get("/records", response_model=AttendanceAdminListResponse)
async def api_get_records(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
) -> AttendanceAdminListResponse:
    """Return attendance records for a given date as JSON."""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    try:
        records = list_attendance_records(date_str)
        return AttendanceAdminListResponse(
            success=True,
            data=records,
            message=f"{len(records)} record(s) for {date_str}",
        )
    except Exception as exc:
        return AttendanceAdminListResponse(
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


@router.get("/export.csv")
async def api_export_records(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
) -> Response:
    """Export attendance records as CSV for reporting."""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    csv_data = export_attendance_csv(date_str)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="attendance_{date_str}.csv"',
        },
    )
