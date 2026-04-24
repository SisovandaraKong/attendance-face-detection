"""Database engine/session management."""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base
from database.seed import ensure_seed_data

DEFAULT_DATABASE_URL = "sqlite:///./attendance.db"


def get_database_url() -> str:
    """Read and normalize the SQLAlchemy database URL."""
    raw_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    if raw_url.startswith("postgres://"):
        # Accept the legacy postgres:// form but run SQLAlchemy with a modern driver URI.
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


DATABASE_URL = get_database_url()
ENGINE_KWARGS = {"future": True, "pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    ENGINE_KWARGS["connect_args"] = {"check_same_thread": False}
else:
    ENGINE_KWARGS["pool_size"] = int(os.getenv("DB_POOL_SIZE", "5"))
    ENGINE_KWARGS["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "10"))

engine = create_engine(DATABASE_URL, **ENGINE_KWARGS)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they do not exist."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        try:
            ensure_seed_data(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session with automatic cleanup."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
