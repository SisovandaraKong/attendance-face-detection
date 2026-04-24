"""Database bootstrap helpers for demo-safe baseline data."""

import os
import pickle
from datetime import time
from pathlib import Path

from sqlalchemy import and_, select

from database.models import Branch, Department, Employee, Shift, SystemUser
from services.auth_service import hash_password


BASE_DIR = Path(__file__).resolve().parents[1]
LABEL_ENCODER_PATH = BASE_DIR / "models" / "label_encoder.pkl"
DATASET_DIR = BASE_DIR / "dataset"


def _normalize_display_name(raw_name: str) -> str:
    return " ".join(raw_name.replace("_", " ").split()).strip()


def _discover_demo_employee_names() -> list[str]:
    names: list[str] = []

    if LABEL_ENCODER_PATH.exists():
        try:
            with LABEL_ENCODER_PATH.open("rb") as fh:
                encoder = pickle.load(fh)
            classes = getattr(encoder, "classes_", [])
            names = [_normalize_display_name(str(name)) for name in classes]
        except Exception:
            names = []

    if not names and DATASET_DIR.exists():
        names = [
            _normalize_display_name(path.name)
            for path in sorted(DATASET_DIR.iterdir())
            if path.is_dir()
        ]

    # Preserve order while dropping blanks/duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _ensure_demo_employees(session, branch: Branch, department: Department) -> None:
    auto_seed = os.getenv("AUTO_SEED_DEMO_EMPLOYEES", "true").strip().lower() not in {"0", "false", "no"}
    if not auto_seed:
        return

    existing_count = session.scalar(select(Employee.id).limit(1))
    if existing_count is not None:
        return

    demo_names = _discover_demo_employee_names()
    for index, full_name in enumerate(demo_names, start=1):
        parts = full_name.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else parts[0]
        session.add(
            Employee(
                employee_code=f"EMP{index:03d}",
                branch_id=branch.id,
                department_id=department.id,
                first_name=first_name,
                last_name=last_name,
                full_name=full_name,
                employment_status="ACTIVE",
                face_enrollment_status="ENROLLED",
                is_active=True,
            )
        )


def ensure_seed_data(session) -> None:
    branch = session.scalar(select(Branch).where(Branch.code == "HQ"))
    if branch is None:
        branch = Branch(code="HQ", name="Headquarters", city="Phnom Penh", is_active=True)
        session.add(branch)
        session.flush()

    department = session.scalar(
        select(Department).where(and_(Department.branch_id == branch.id, Department.code == "OPS"))
    )
    if department is None:
        department = Department(
            branch_id=branch.id,
            code="OPS",
            name="Operations",
            is_active=True,
        )
        session.add(department)
        session.flush()

    shift = session.scalar(select(Shift).where(Shift.code == "GENERAL"))
    if shift is None:
        shift = Shift(
            code="GENERAL",
            name="Bank Office Shift",
            start_time=time(hour=8, minute=0),
            end_time=time(hour=17, minute=0),
            grace_minutes=10,
            late_after_minutes=10,
            min_checkout_time=time(hour=16, minute=30),
            is_overnight=False,
            is_active=True,
        )
        session.add(shift)
        session.flush()

    _ensure_demo_employees(session, branch, department)

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@bank.local")

    super_admin = session.scalar(select(SystemUser).where(SystemUser.username == admin_username))
    if super_admin is None:
        session.add(
            SystemUser(
                username=admin_username,
                password_hash=hash_password(admin_password),
                full_name="System Administrator",
                email=admin_email,
                role="super_admin",
                branch_id=branch.id,
                department_id=department.id,
                is_active=True,
            )
        )

    hr_username = os.getenv("HR_ADMIN_USERNAME", "hradmin")
    hr_password = os.getenv("HR_ADMIN_PASSWORD", "hradmin123")
    hr_email = os.getenv("HR_ADMIN_EMAIL", "hr@bank.local")

    hr_admin = session.scalar(select(SystemUser).where(SystemUser.username == hr_username))
    if hr_admin is None:
        session.add(
            SystemUser(
                username=hr_username,
                password_hash=hash_password(hr_password),
                full_name="HR Administrator",
                email=hr_email,
                role="hr_admin",
                branch_id=branch.id,
                department_id=department.id,
                is_active=True,
            )
        )
