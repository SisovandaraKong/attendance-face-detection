"""Employee registration and management business logic."""

from decimal import Decimal

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.employee import Employee
from app.models.user import User
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.services.errors import ConflictError, NotFoundError, ServiceError
from app.services.face_service import FACE_STORAGE_DIR, extract_embedding, verify_face_quality


async def inspect_face(face_image: bytes) -> dict:
    """Return face quality status without creating or updating an employee."""
    quality = verify_face_quality(face_image)
    return {"success": True, "data": quality, "message": quality["message"]}


async def create_employee(data: EmployeeCreate, face_image: bytes, db: AsyncSession) -> dict:
    """Create an employee only after face quality validation succeeds."""
    quality = verify_face_quality(face_image)
    if not quality["valid"]:
        raise ServiceError(quality["message"], status_code=400)

    existing_email = await db.scalar(select(Employee).where(Employee.email == data.email))
    if existing_email is not None:
        raise ConflictError("Employee email already exists")

    username = data.username or data.email.split("@", maxsplit=1)[0]
    existing_user = await db.scalar(select(User).where(User.username == username))
    if existing_user is not None:
        raise ConflictError("Username already exists")

    embedding = extract_embedding(face_image)
    employee = Employee(
        name=data.name,
        email=str(data.email),
        phone=data.phone,
        department=data.department,
        position=data.position,
        salary_type=data.salary_type,
        base_salary=Decimal(data.base_salary),
        bank_account=data.bank_account,
        join_date=data.join_date,
        status=data.status,
        face_embedding=embedding,
    )
    db.add(employee)
    await db.flush()

    face_path = _save_face_image(face_image, employee.id)
    employee.face_image_path = face_path
    db.add(
        User(
            employee_id=employee.id,
            username=username,
            hashed_password=get_password_hash(data.temp_password),
            role="employee",
            is_active=True,
        )
    )
    await db.commit()
    await db.refresh(employee)
    return {"success": True, "data": _employee_to_dict(employee), "message": "Employee created"}


async def list_employees(db: AsyncSession) -> dict:
    result = await db.execute(select(Employee).order_by(Employee.name))
    return {
        "success": True,
        "data": [_employee_to_dict(employee) for employee in result.scalars().all()],
        "message": "Employees loaded",
    }


async def get_employee(employee_id: int, db: AsyncSession) -> dict:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")
    return {"success": True, "data": _employee_to_dict(employee), "message": "Employee loaded"}


async def update_employee(employee_id: int, data: EmployeeUpdate, db: AsyncSession) -> dict:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(employee, key, value)
    await db.commit()
    await db.refresh(employee)
    return {"success": True, "data": _employee_to_dict(employee), "message": "Employee updated"}


async def deactivate_employee(employee_id: int, db: AsyncSession) -> dict:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")
    employee.status = "inactive"
    user = await db.scalar(select(User).where(User.employee_id == employee_id))
    if user is not None:
        user.is_active = False
    await db.commit()
    return {"success": True, "data": {"id": employee_id}, "message": "Employee deactivated"}


async def reregister_face(employee_id: int, face_image: bytes, db: AsyncSession) -> dict:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")
    quality = verify_face_quality(face_image)
    if not quality["valid"]:
        raise ServiceError(quality["message"], status_code=400)
    employee.face_embedding = extract_embedding(face_image)
    employee.face_image_path = _save_face_image(face_image, employee.id)
    await db.commit()
    await db.refresh(employee)
    return {"success": True, "data": _employee_to_dict(employee), "message": "Face re-registered"}


def _save_face_image(image_bytes: bytes, employee_id: int) -> str:
    FACE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = FACE_STORAGE_DIR / f"{employee_id}.jpg"
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ServiceError("Invalid face image", status_code=400)
    if not cv2.imwrite(str(path), image):
        raise ServiceError("Failed to save face image", status_code=500)
    return str(path)


def _employee_to_dict(employee: Employee) -> dict:
    return {
        "id": employee.id,
        "name": employee.name,
        "email": employee.email,
        "phone": employee.phone,
        "department": employee.department,
        "position": employee.position,
        "salary_type": employee.salary_type,
        "base_salary": str(employee.base_salary),
        "bank_account": employee.bank_account,
        "join_date": employee.join_date.isoformat(),
        "status": employee.status,
        "face_image_path": employee.face_image_path,
        "created_at": employee.created_at.isoformat() if employee.created_at else None,
        "updated_at": employee.updated_at.isoformat() if employee.updated_at else None,
    }
