"""Seed default payroll data: standard work schedule and admin/admin123 user."""

import asyncio
from datetime import time

from sqlalchemy import select

from app.core.security import get_password_hash
from app.database import AsyncSessionLocal, init_db
from app.models.attendance import WorkSchedule
from app.models.user import User


async def seed() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        schedule = await db.scalar(select(WorkSchedule).where(WorkSchedule.name == "Standard"))
        if schedule is None:
            db.add(
                WorkSchedule(
                    name="Standard",
                    work_start=time(hour=8),
                    work_end=time(hour=17),
                    late_threshold_minutes=15,
                )
            )

        admin = await db.scalar(select(User).where(User.username == "admin"))
        if admin is None:
            db.add(
                User(
                    employee_id=None,
                    username="admin",
                    hashed_password=get_password_hash("admin123"),
                    role="admin",
                    is_active=True,
                )
            )

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
