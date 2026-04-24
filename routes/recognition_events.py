"""Recognition event APIs for reviewing AI inference evidence."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from dependencies.auth import require_roles
from schemas.attendance import APIResponse, RecognitionEventListResponse
from services.attendance_service import get_recognition_event_stats, list_recognition_events

router = APIRouter(
    prefix="/api/admin/recognition-events",
    tags=["admin-recognition-events"],
    dependencies=[Depends(require_roles("super_admin", "hr_admin"))],
)


@router.get("", response_model=RecognitionEventListResponse)
async def api_list_recognition_events(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    match_result: Optional[str] = Query(
        default=None,
        description="MATCHED, LOW_LIVENESS, DUPLICATE_IGNORED, OUTSIDE_SHIFT_WINDOW, UNREGISTERED, UNKNOWN",
    ),
) -> RecognitionEventListResponse:
    """Return recent recognition events for AI evidence review."""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    events = list_recognition_events(date_str=date_str, match_result=match_result)
    return RecognitionEventListResponse(
        success=True,
        data=events,
        message=f"{len(events)} recognition event(s) for {date_str}",
    )


@router.get("/stats", response_model=APIResponse)
async def api_recognition_event_stats(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
) -> APIResponse:
    """Return aggregate recognition-event statistics for a day."""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    stats = get_recognition_event_stats(date_str)
    return APIResponse(
        success=True,
        data=stats.model_dump(),
        message=f"Recognition stats for {date_str}",
    )
