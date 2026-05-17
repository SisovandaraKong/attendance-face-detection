"""Leave routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.user import User
from app.schemas.leave import LeaveCreate
from app.services import leave_service
from app.routes._errors import run_service


router = APIRouter(prefix="/api/leaves", tags=["leaves"])


@router.post("")
async def submit_leave(
    payload: LeaveCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr", "employee")),
):
    return await run_service(
        lambda: leave_service.submit_leave_request(
            payload.employee_id,
            payload.leave_type,
            payload.start_date,
            payload.end_date,
            payload.reason,
            db,
        )
    )


@router.get("")
async def list_leaves(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: leave_service.list_leaves(db, status))


@router.put("/{leave_id}/approve")
async def approve_leave(
    leave_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: leave_service.approve_leave(leave_id, current_user.id, db))


@router.put("/{leave_id}/reject")
async def reject_leave(
    leave_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: leave_service.reject_leave(leave_id, current_user.id, db))


@router.get("/{employee_id}")
async def employee_leaves(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr", "employee")),
):
    return await run_service(lambda: leave_service.list_employee_leaves(employee_id, db))
