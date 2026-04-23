"""
routes/attendance.py
─────────────────────────────────────────────────────────────
Attendance log page + JSON API endpoints.
─────────────────────────────────────────────────────────────
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from schemas.attendance import APIResponse, AttendanceListResponse
from services.attendance_service import list_log_dates, read_log

router    = APIRouter(prefix="/attendance", tags=["attendance"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def attendance_page(
    request: Request,
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
) -> HTMLResponse:
    """Attendance log page — filterable by date."""
    today      = datetime.now().strftime("%Y-%m-%d")
    date_str   = date or today
    records    = read_log(date_str)
    all_dates  = list_log_dates()

    return templates.TemplateResponse(request, "attendance.html", {
        "date":      date_str,
        "records":   records,
        "all_dates": all_dates,
        "today":     today,
    })


# ── JSON API ─────────────────────────────────────────────────

@router.get("/api/records", response_model=AttendanceListResponse)
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


@router.get("/api/dates", response_model=APIResponse)
async def api_list_dates() -> APIResponse:
    """Return all dates that have attendance log files."""
    return APIResponse(
        success=True,
        data=list_log_dates(),
        message="Available log dates",
    )
