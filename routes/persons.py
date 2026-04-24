"""
routes/persons.py
─────────────────────────────────────────────────────────────
Person management JSON API for admin portal.

Shows registered employees, their face-enrollment readiness,
and how many dataset images exist for each person.
─────────────────────────────────────────────────────────────
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from dependencies.auth import require_roles
from database.models import Branch, Department, Employee
from database.session import get_db_session
from schemas.attendance import (
    APIResponse,
    EmployeeCreateRequest,
    EmployeeUpdateRequest,
    PersonInfo,
    PersonListResponse,
)
from services.attendance_service import _ensure_baseline_entities
from services.audit_service import write_audit_log

router = APIRouter(
    prefix="/api/admin/persons",
    tags=["admin-persons"],
    dependencies=[Depends(require_roles("super_admin", "hr_admin"))],
)

# Paths from project root
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR  = os.path.join(BASE_DIR, "dataset")

# 7 zones × 30 images × 5 augmentations = 1050 images per person
IMAGES_PER_ZONE    = 30
NUM_ZONES          = 7
AUGMENT_FACTOR     = 5
TOTAL_IMAGES_NEEDED = IMAGES_PER_ZONE * NUM_ZONES * AUGMENT_FACTOR


def _dataset_key(name: str) -> str:
    return "_".join(name.strip().split())


def _dataset_counts() -> dict[str, int]:
    if not os.path.isdir(DATASET_DIR):
        return {}

    counts: dict[str, int] = {}
    for name in sorted(os.listdir(DATASET_DIR)):
        person_path = os.path.join(DATASET_DIR, name)
        if not os.path.isdir(person_path):
            continue
        count = len([
            f for f in os.listdir(person_path)
            if f.lower().endswith((".jpg", ".png", ".jpeg"))
        ])
        counts[name] = count
    return counts


def _list_persons() -> list[PersonInfo]:
    """Build employee-backed enrollment cards enriched with dataset counts."""
    dataset_counts = _dataset_counts()

    with get_db_session() as session:
        rows = session.execute(
            select(Employee, Branch, Department)
            .join(Branch, Branch.id == Employee.branch_id)
            .join(Department, Department.id == Employee.department_id)
            .order_by(Employee.full_name.asc())
        ).all()

    persons = []
    for employee, branch, department in rows:
        dataset_key = _dataset_key(employee.full_name)
        image_count = dataset_counts.get(dataset_key, 0)
        persons.append(PersonInfo(
            id=employee.id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            branch_name=branch.name,
            department_name=department.name,
            employment_status=employee.employment_status,
            enrollment_status=employee.face_enrollment_status,
            dataset_key=dataset_key,
            image_count=image_count,
            complete=(image_count >= TOTAL_IMAGES_NEEDED),
            is_active=employee.is_active,
        ))
    return persons


@router.post("", response_model=APIResponse)
async def api_create_person(payload: EmployeeCreateRequest) -> APIResponse:
    """Register an employee before face enrollment begins."""
    full_name = " ".join(payload.full_name.strip().split())
    if not full_name:
        raise HTTPException(status_code=400, detail="Full name is required")

    parts = full_name.split()
    first_name = parts[0]
    last_name = " ".join(parts[1:]) if len(parts) > 1 else parts[0]

    with get_db_session() as session:
        existing = session.scalar(
            select(Employee).where(Employee.employee_code == payload.employee_code.strip())
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Employee code already exists")

        branch, department, _, _ = _ensure_baseline_entities(session)

        employee = Employee(
            employee_code=payload.employee_code.strip(),
            branch_id=branch.id,
            department_id=department.id,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            email=payload.email.strip() if payload.email else None,
            employment_status="ACTIVE",
            face_enrollment_status="NOT_ENROLLED",
            is_active=True,
        )
        session.add(employee)
        session.flush()

    write_audit_log(
        action="EMPLOYEE_CREATE",
        entity_type="employee",
        entity_id=str(employee.id),
        new_values={
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "email": employee.email,
        },
    )

    return APIResponse(
        success=True,
        data={"employee_id": employee.id, "employee_code": employee.employee_code},
        message="Employee created",
    )


@router.patch("/{employee_id}", response_model=APIResponse)
async def api_update_person(employee_id: int, payload: EmployeeUpdateRequest) -> APIResponse:
    """Update employee operational fields."""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return APIResponse(success=True, data={"employee_id": employee_id}, message="No changes applied")

    with get_db_session() as session:
        employee = session.get(Employee, employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")

        old_values = {
            "full_name": employee.full_name,
            "email": employee.email,
            "employment_status": employee.employment_status,
            "face_enrollment_status": employee.face_enrollment_status,
            "is_active": employee.is_active,
        }

        if "full_name" in changes and changes["full_name"]:
            full_name = " ".join(changes["full_name"].strip().split())
            parts = full_name.split()
            employee.full_name = full_name
            employee.first_name = parts[0]
            employee.last_name = " ".join(parts[1:]) if len(parts) > 1 else parts[0]
        if "email" in changes:
            employee.email = changes["email"].strip() if changes["email"] else None
        if "employment_status" in changes and changes["employment_status"]:
            employee.employment_status = changes["employment_status"].upper()
        if "face_enrollment_status" in changes and changes["face_enrollment_status"]:
            employee.face_enrollment_status = changes["face_enrollment_status"].upper()
        if "is_active" in changes:
            employee.is_active = bool(changes["is_active"])
        session.flush()

        new_values = {
            "full_name": employee.full_name,
            "email": employee.email,
            "employment_status": employee.employment_status,
            "face_enrollment_status": employee.face_enrollment_status,
            "is_active": employee.is_active,
        }

    write_audit_log(
        action="EMPLOYEE_UPDATE",
        entity_type="employee",
        entity_id=str(employee_id),
        old_values=old_values,
        new_values=new_values,
    )

    return APIResponse(
        success=True,
        data={"employee_id": employee_id},
        message="Employee updated",
    )

@router.get("/list", response_model=PersonListResponse)
async def api_list_persons() -> PersonListResponse:
    """Return all enrolled persons with dataset completion status."""
    try:
        persons = _list_persons()
        return PersonListResponse(
            success=True,
            data=persons,
            message=f"{len(persons)} person(s) enrolled",
        )
    except Exception as exc:
        return PersonListResponse(
            success=False,
            data=[],
            message=str(exc),
        )


@router.get("/stats", response_model=APIResponse)
async def api_person_stats() -> APIResponse:
    """Return aggregate dataset stats."""
    persons = _list_persons()
    total_images = sum(p.image_count for p in persons)
    complete     = sum(1 for p in persons if p.complete)
    return APIResponse(
        success=True,
        data={
            "total_persons": len(persons),
            "complete":      complete,
            "incomplete":    len(persons) - complete,
            "total_images":  total_images,
            "total_needed_per_person": TOTAL_IMAGES_NEEDED,
        },
        message="Dataset statistics",
    )
