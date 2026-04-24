"""
routes/public.py
─────────────────────────────────────────────────────────────
Public page routes (Jinja2).
Only this page remains template-rendered; admin UI lives in Next.js.
─────────────────────────────────────────────────────────────
"""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from schemas.attendance import APIResponse
from services.attendance_service import read_log

router = APIRouter(tags=["public"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def public_page(request: Request) -> HTMLResponse:
    """Public face detection page with live stream."""
    face_service = request.app.state.face_service
    today = datetime.now().strftime("%Y-%m-%d")
    records = read_log(today)

    return templates.TemplateResponse(
        request,
        "public.html",
        {
            "model_ready": face_service.is_ready,
            "today_count": len(records),
            "today_records": records[-10:],
        },
    )


@router.get("/api/public/recent", response_model=APIResponse)
async def api_public_recent() -> APIResponse:
    """Return the most recent attendance records from today for public page polling."""
    today = datetime.now().strftime("%Y-%m-%d")
    records = read_log(today)
    return APIResponse(
        success=True,
        data={
            "today": today,
            "today_count": len(records),
            "records": records[-10:],
        },
        message="Latest recognitions",
    )


@router.get("/api/public/status", response_model=APIResponse)
async def api_public_status(request: Request) -> APIResponse:
    """Return the latest kiosk recognition/liveness status for the public page."""
    face_service = request.app.state.face_service
    return APIResponse(
        success=True,
        data=face_service.public_status,
        message="Latest kiosk status",
    )
