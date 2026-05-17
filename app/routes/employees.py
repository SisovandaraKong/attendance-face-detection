"""Employee routes."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.user import User
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.services import employee_service
from app.routes._errors import run_service


router = APIRouter(prefix="/api/employees", tags=["employees"])


@router.get("")
async def list_employees(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: employee_service.list_employees(db))


@router.post("")
async def create_employee(
    name: str = Form(...),
    email: str = Form(...),
    phone: str | None = Form(None),
    department: str = Form(...),
    position: str = Form(...),
    salary_type: str = Form("monthly"),
    base_salary: Decimal = Form(...),
    bank_account: str | None = Form(None),
    join_date: date = Form(...),
    status: str = Form("active"),
    username: str | None = Form(None),
    temp_password: str = Form("Temp12345"),
    face_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    payload = EmployeeCreate(
        name=name,
        email=email,
        phone=phone,
        department=department,
        position=position,
        salary_type=salary_type,
        base_salary=base_salary,
        bank_account=bank_account,
        join_date=join_date,
        status=status,
        username=username,
        temp_password=temp_password,
    )
    image_bytes = await face_image.read()
    return await run_service(lambda: employee_service.create_employee(payload, image_bytes, db))


@router.post("/face-quality")
async def inspect_face_quality(
    face_image: UploadFile = File(...),
    _: User = Depends(require_roles("admin", "hr")),
):
    image_bytes = await face_image.read()
    return await run_service(lambda: employee_service.inspect_face(image_bytes))


@router.get("/{employee_id}")
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr", "employee")),
):
    return await run_service(lambda: employee_service.get_employee(employee_id, db))


@router.put("/{employee_id}")
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: employee_service.update_employee(employee_id, payload, db))


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    return await run_service(lambda: employee_service.deactivate_employee(employee_id, db))


@router.post("/{employee_id}/re-register-face")
async def reregister_face(
    employee_id: int,
    face_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "hr")),
):
    image_bytes = await face_image.read()
    return await run_service(lambda: employee_service.reregister_face(employee_id, image_bytes, db))
