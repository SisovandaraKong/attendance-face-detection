"""
routes/dashboard.py
─────────────────────────────────────────────────────────────
Dashboard page — live webcam view + today's attendance summary.
─────────────────────────────────────────────────────────────
"""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services.attendance_service import get_summary, read_log

router    = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse, tags=["pages"])
async def dashboard(request: Request) -> HTMLResponse:
    """Main dashboard page with live feed and today's attendance."""
    today        = datetime.now().strftime("%Y-%m-%d")
    today_log    = read_log(today)
    weekly       = get_summary()
    face_service = request.app.state.face_service

    return templates.TemplateResponse(request, "dashboard.html", {
        "today":         today,
        "today_count":   len(today_log),
        "today_records": today_log[-10:],        # last 10 for sidebar preview
        "weekly_data":   weekly,
        "model_ready":   face_service.is_ready,
        "known_persons": face_service.known_persons,
    })
