"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the payroll management API."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Payroll Management System"
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/payroll_management",
        validation_alias="DATABASE_URL",
    )
    secret_key: str = Field(default="change-me-in-production", validation_alias="SECRET_KEY")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    late_penalty_amount: float = 5.00
    face_storage_dir: Path = Path("storage/faces")
    attendance_storage_dir: Path = Path("storage/attendance")
    payslip_storage_dir: Path = Path("storage/payslips")
    templates_dir: Path = Path("app/templates")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
