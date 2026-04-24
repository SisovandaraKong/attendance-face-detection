"""
routes/dashboard.py
─────────────────────────────────────────────────────────────
Admin dashboard JSON API.
─────────────────────────────────────────────────────────────
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request

from dependencies.auth import require_roles
from schemas.attendance import APIResponse
from services.attendance_service import (
    get_recognition_event_stats,
    get_report_summary,
    get_summary,
    get_late_trend,
    read_log,
)

router = APIRouter(
    prefix="/api/admin/dashboard",
    tags=["admin-dashboard"],
    dependencies=[Depends(require_roles("super_admin", "hr_admin"))],
)


@router.get("/summary", response_model=APIResponse)
async def api_dashboard_summary(request: Request) -> APIResponse:
    """Return live dashboard summary data for the admin portal."""
    today = datetime.now().strftime("%Y-%m-%d")
    today_log = read_log(today)
    weekly = get_summary()
    late_trend = get_late_trend()
    event_stats = get_recognition_event_stats(today)
    report_summary = get_report_summary(today)
    face_service = request.app.state.face_service

    return APIResponse(
        success=True,
        data={
            "today": today,
            "today_count": len(today_log),
            "today_records": today_log[-10:],
            "weekly_data": weekly,
            "late_trend": late_trend,
            "model_ready": face_service.is_ready,
            "known_persons": face_service.known_persons,
            "known_persons_count": len(face_service.known_persons),
            "days_logged": len(weekly),
            "recognition_stats": event_stats.model_dump(),
            "report_summary": report_summary.model_dump(),
        },
        message="Dashboard summary",
    )
