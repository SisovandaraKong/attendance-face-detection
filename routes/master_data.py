"""Master-data endpoints for branches and shifts."""

from fastapi import APIRouter, Depends

from dependencies.auth import require_roles
from schemas.attendance import APIResponse
from services.attendance_service import list_branches, list_shifts

router = APIRouter(
    prefix="/api/admin/master-data",
    tags=["admin-master-data"],
    dependencies=[Depends(require_roles("super_admin", "hr_admin"))],
)


@router.get("/branches", response_model=APIResponse)
async def api_branches() -> APIResponse:
    return APIResponse(success=True, data=[b.model_dump() for b in list_branches()], message="Branches")


@router.get("/shifts", response_model=APIResponse)
async def api_shifts() -> APIResponse:
    return APIResponse(success=True, data=[s.model_dump() for s in list_shifts()], message="Shifts")
