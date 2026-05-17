"""Async SQLAlchemy database setup for the attendance management system."""

from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.base import Base

load_dotenv()


def _database_url() -> str:
    url = get_settings().database_url

    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


DATABASE_URL = _database_url()
settings = get_settings()

_engine_kwargs: dict = {
    "echo": settings.sql_echo,
    "pool_pre_ping": True,
}

if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = settings.db_pool_size
    _engine_kwargs["max_overflow"] = settings.db_max_overflow

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields one async DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables in development; production should use Alembic migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
