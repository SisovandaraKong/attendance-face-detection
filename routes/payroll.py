"""Payroll administration endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.session import get_db
from dependencies.auth import get_current_admin_user, require_roles
from schemas.attendance import APIResponse
from schemas.payroll import (
    DeductionRuleCreate,
    DeductionRuleResponse,
    DeductionRuleToggleRequest,
    PayrollRunRequest,
    SalaryConfigCreate,
    SalaryConfigResponse,
)
from services.payroll_service import payroll_service

router = APIRouter(
    prefix="/api/admin/payroll",
    tags=["admin-payroll"],
)


@router.post("/run", response_model=APIResponse, dependencies=[Depends(require_roles("super_admin"))])
async def api_run_payroll(
    payload: PayrollRunRequest,
    db: Session = Depends(get_db),
) -> APIResponse:
    records = payroll_service.run_payroll(
        period_month=payload.period_month,
        period_year=payload.period_year,
        employee_ids=payload.employee_ids,
        db=db,
    )
    response_rows = [payroll_service.get_payroll_record(record.id, db).model_dump() for record in records]
    return APIResponse(success=True, data=response_rows, message=f"Processed {len(response_rows)} payroll record(s)")


@router.get("/records", response_model=APIResponse)
async def api_get_payroll_records(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=9999),
    status: str | None = Query(default=None),
    _: object = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    records = payroll_service.get_payroll_records(period_month=month, period_year=year, status_value=status, db=db)
    return APIResponse(
        success=True,
        data=[record.model_dump() for record in records],
        message=f"{len(records)} payroll record(s)",
    )


@router.get("/records/{record_id}", response_model=APIResponse)
async def api_get_payroll_record(
    record_id: int,
    _: object = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    record = payroll_service.get_payroll_record(record_id, db)
    return APIResponse(success=True, data=record.model_dump(), message="Payroll record detail")


@router.post(
    "/records/{record_id}/approve",
    response_model=APIResponse,
    dependencies=[Depends(require_roles("super_admin"))],
)
async def api_approve_payroll(
    record_id: int,
    current_user=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    record = payroll_service.approve_payroll(record_id, current_user.id, db)
    response_row = payroll_service.get_payroll_record(record.id, db)
    return APIResponse(success=True, data=response_row.model_dump(), message="Payroll record approved")


@router.get("/reports/summary", response_model=APIResponse)
async def api_get_payroll_summary(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=9999),
    _: object = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> APIResponse:
    summary = payroll_service.get_payroll_summary(month, year, db)
    return APIResponse(success=True, data=summary.model_dump(), message="Payroll summary")


@router.get(
    "/salary-configs",
    response_model=APIResponse,
    dependencies=[Depends(require_roles("super_admin"))],
)
async def api_list_salary_configs(
    db: Session = Depends(get_db),
) -> APIResponse:
    configs = [SalaryConfigResponse.model_validate(row).model_dump() for row in payroll_service.list_salary_configs(db)]
    return APIResponse(success=True, data=configs, message=f"{len(configs)} salary config(s)")


@router.post(
    "/salary-configs",
    response_model=APIResponse,
    dependencies=[Depends(require_roles("super_admin"))],
)
async def api_create_salary_config(
    payload: SalaryConfigCreate,
    db: Session = Depends(get_db),
) -> APIResponse:
    config = payroll_service.create_salary_config(db=db, **payload.model_dump())
    return APIResponse(
        success=True,
        data=SalaryConfigResponse.model_validate(config).model_dump(),
        message="Salary config created",
    )


@router.get(
    "/deduction-rules",
    response_model=APIResponse,
    dependencies=[Depends(require_roles("super_admin"))],
)
async def api_list_deduction_rules(
    db: Session = Depends(get_db),
) -> APIResponse:
    rules = [DeductionRuleResponse.model_validate(row).model_dump() for row in payroll_service.list_deduction_rules(db)]
    return APIResponse(success=True, data=rules, message=f"{len(rules)} deduction rule(s)")


@router.post(
    "/deduction-rules",
    response_model=APIResponse,
    dependencies=[Depends(require_roles("super_admin"))],
)
async def api_create_deduction_rule(
    payload: DeductionRuleCreate,
    db: Session = Depends(get_db),
) -> APIResponse:
    rule = payroll_service.create_deduction_rule(db=db, **payload.model_dump())
    return APIResponse(
        success=True,
        data=DeductionRuleResponse.model_validate(rule).model_dump(),
        message="Deduction rule created",
    )


@router.patch(
    "/deduction-rules/{rule_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_roles("super_admin"))],
)
async def api_toggle_deduction_rule(
    rule_id: int,
    payload: DeductionRuleToggleRequest,
    db: Session = Depends(get_db),
) -> APIResponse:
    rule = payroll_service.toggle_deduction_rule(rule_id, payload.is_active, db)
    return APIResponse(
        success=True,
        data=DeductionRuleResponse.model_validate(rule).model_dump(),
        message="Deduction rule updated",
    )
