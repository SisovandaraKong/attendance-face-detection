"""Reporting APIs for admin dashboards and thesis analytics."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from dependencies.auth import require_roles
from schemas.attendance import APIResponse
from services.attendance_service import get_report_summary

router = APIRouter(
    prefix="/api/admin/reports",
    tags=["admin-reports"],
    dependencies=[Depends(require_roles("super_admin", "hr_admin"))],
)


@router.get("/summary", response_model=APIResponse)
async def api_report_summary(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
) -> APIResponse:
    """Return summary analytics for a given day."""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    summary = get_report_summary(date_str)
    return APIResponse(
        success=True,
        data=summary.model_dump(),
        message=f"Report summary for {date_str}",
    )
