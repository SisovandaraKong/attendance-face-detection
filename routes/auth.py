"""Authentication endpoints for admin users."""

from fastapi import APIRouter, Depends, HTTPException

from dependencies.auth import get_current_admin_user
from database.models import SystemUser
from schemas.attendance import APIResponse, LoginRequest, LoginResponse
from services.audit_service import write_audit_log
from services.auth_service import authenticate_user, create_access_token, normalize_role

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=APIResponse)
async def api_login(payload: LoginRequest) -> APIResponse:
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        write_audit_log(
            action="LOGIN_ATTEMPT",
            entity_type="system_user",
            entity_id=payload.username,
            result="FAILED",
            reason="invalid_credentials",
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user)
    write_audit_log(
        action="LOGIN_ATTEMPT",
        entity_type="system_user",
        entity_id=str(user.id),
        result="SUCCESS",
    )
    return APIResponse(
        success=True,
        data=LoginResponse(
            access_token=token,
            username=user.username,
            role=normalize_role(user.role),
            full_name=user.full_name,
        ).model_dump(),
        message="Login successful",
    )


@router.get("/me", response_model=APIResponse)
async def api_me(user: SystemUser = Depends(get_current_admin_user)) -> APIResponse:
    return APIResponse(
        success=True,
        data={
            "username": user.username,
            "full_name": user.full_name,
            "role": normalize_role(user.role),
            "branch_id": user.branch_id,
            "department_id": user.department_id,
        },
        message="Authenticated user",
    )


@router.post("/logout", response_model=APIResponse)
async def api_logout(user: SystemUser = Depends(get_current_admin_user)) -> APIResponse:
    write_audit_log(
        action="LOGOUT",
        entity_type="system_user",
        entity_id=str(user.id),
        result="SUCCESS",
    )
    return APIResponse(success=True, data={"logged_out": True}, message="Logout successful")
