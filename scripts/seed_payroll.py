"""Seed default payroll data from environment variables."""

import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal, init_db
from app.services.bootstrap_service import ensure_bootstrap_data


async def seed() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        await ensure_bootstrap_data(db)


if __name__ == "__main__":
    asyncio.run(seed())
