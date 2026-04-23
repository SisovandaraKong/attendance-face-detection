"""
routes/dashboard.py
─────────────────────────────────────────────────────────────
Admin dashboard JSON API.
─────────────────────────────────────────────────────────────
"""

from datetime import datetime

from fastapi import APIRouter, Request

from schemas.attendance import APIResponse
from services.attendance_service import get_summary, read_log

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])


@router.get("/summary", response_model=APIResponse)
async def api_dashboard_summary(request: Request) -> APIResponse:
    """Return live dashboard summary data for the admin portal."""
    today = datetime.now().strftime("%Y-%m-%d")
    today_log = read_log(today)
    weekly = get_summary()
    face_service = request.app.state.face_service

    return APIResponse(
        success=True,
        data={
            "today": today,
            "today_count": len(today_log),
            "today_records": today_log[-10:],
            "weekly_data": weekly,
            "model_ready": face_service.is_ready,
            "known_persons": face_service.known_persons,
            "known_persons_count": len(face_service.known_persons),
            "days_logged": len(weekly),
        },
        message="Dashboard summary",
    )
