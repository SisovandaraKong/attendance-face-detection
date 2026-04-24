"""System and health endpoints for admin monitoring."""

from fastapi import APIRouter, Depends, Request

from dependencies.auth import require_roles
from schemas.attendance import APIResponse
from services.attendance_service import get_system_health

router = APIRouter(
    prefix="/api/admin/system",
    tags=["admin-system"],
    dependencies=[Depends(require_roles("super_admin"))],
)


@router.get("/health", response_model=APIResponse)
async def api_health(request: Request) -> APIResponse:
    face_service = request.app.state.face_service
    health = get_system_health(
        model_ready=face_service.is_ready,
        known_persons_count=len(face_service.known_persons),
    )
    return APIResponse(success=True, data=health.model_dump(), message="System health")
