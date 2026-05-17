"""Environment-driven database bootstrap helpers."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from pathlib import Path
import pickle
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import get_password_hash, verify_password
from app.models.attendance import WorkSchedule
from app.models.employee import Employee
from app.models.user import User


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABEL_ENCODER_PATH = PROJECT_ROOT / "models" / "label_encoder.pkl"
DATASET_DIR = PROJECT_ROOT / "dataset"
DEMO_EMAIL_DOMAIN = "demo.bank.local"


async def ensure_bootstrap_data(db: AsyncSession) -> None:
    """Create or update required startup data from environment variables."""
    settings = get_settings()

    await _ensure_standard_schedule(db)
    await _ensure_staff_user(
        db,
        username=settings.admin_username,
        password=settings.admin_password,
        role="admin",
        email=settings.admin_email,
        name="System Administrator",
        department="Administration",
        position="System Administrator",
    )
    await _ensure_staff_user(
        db,
        username=settings.hr_admin_username,
        password=settings.hr_admin_password,
        role="hr",
        email=settings.hr_admin_email,
        name="HR Administrator",
        department="Human Resources",
        position="HR Administrator",
    )

    if settings.auto_seed_demo_employees:
        await _ensure_demo_employees(db)

    await db.commit()


async def _ensure_standard_schedule(db: AsyncSession) -> None:
    schedule = await db.scalar(select(WorkSchedule).where(WorkSchedule.name == "Standard"))
    if schedule is not None:
        return

    db.add(
        WorkSchedule(
            name="Standard",
            work_start=time(hour=8),
            work_end=time(hour=17),
            late_threshold_minutes=15,
        )
    )


async def _ensure_staff_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    role: str,
    email: str,
    name: str,
    department: str,
    position: str,
) -> None:
    employee = await _ensure_staff_employee(
        db,
        email=email,
        name=name,
        department=department,
        position=position,
    )
    await db.flush()

    user = await db.scalar(select(User).where(User.username == username))
    if user is None:
        db.add(
            User(
                employee_id=employee.id,
                username=username,
                hashed_password=get_password_hash(password),
                role=role,
                is_active=True,
            )
        )
        return

    user.employee_id = employee.id
    if not verify_password(password, user.hashed_password):
        user.hashed_password = get_password_hash(password)
    user.role = role
    user.is_active = True


async def _ensure_staff_employee(
    db: AsyncSession,
    *,
    email: str,
    name: str,
    department: str,
    position: str,
) -> Employee:
    normalized_email = email.strip().lower()
    employee = await db.scalar(select(Employee).where(Employee.email == normalized_email))
    if employee is None:
        employee = Employee(
            name=name,
            email=normalized_email,
            phone=None,
            department=department,
            position=position,
            salary_type="monthly",
            base_salary=Decimal("0.00"),
            bank_account=None,
            join_date=date.today(),
            status="active",
            face_embedding=None,
            face_image_path=None,
        )
        db.add(employee)
        return employee

    employee.name = name
    employee.department = department
    employee.position = position
    employee.salary_type = "monthly"
    employee.status = "active"
    return employee


async def _ensure_demo_employees(db: AsyncSession) -> None:
    demo_names = _discover_demo_employee_names()
    for index, name in enumerate(demo_names, start=1):
        email = f"{_slugify(name) or f'employee-{index}'}@{DEMO_EMAIL_DOMAIN}"
        employee = await db.scalar(select(Employee).where(Employee.email == email))
        if employee is not None:
            continue

        db.add(
            Employee(
                name=name,
                email=email,
                phone=None,
                department="Operations",
                position="Employee",
                salary_type="monthly",
                base_salary=Decimal("500.00"),
                bank_account=None,
                join_date=date.today(),
                status="active",
                face_embedding=None,
                face_image_path=None,
            )
        )


def _discover_demo_employee_names() -> list[str]:
    names: list[str] = []
    if LABEL_ENCODER_PATH.exists():
        try:
            with LABEL_ENCODER_PATH.open("rb") as handle:
                encoder = pickle.load(handle)
            names = [_normalize_display_name(str(value)) for value in getattr(encoder, "classes_", [])]
        except Exception:
            names = []

    if not names and DATASET_DIR.exists():
        names = [
            _normalize_display_name(path.name)
            for path in sorted(DATASET_DIR.iterdir())
            if path.is_dir()
        ]

    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _normalize_display_name(value: str) -> str:
    return " ".join(value.replace("_", " ").split()).strip()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", ".", value.strip().lower()).strip(".")
    return re.sub(r"\.+", ".", slug)
