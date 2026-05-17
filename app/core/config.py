"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the payroll management API."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Payroll Management System"
    database_url: str = "sqlite+aiosqlite:///attendance.db"
    sql_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    admin_origin: str = "http://localhost:3000"
    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_email: str = "admin@bank.local"
    hr_admin_username: str = "hradmin"
    hr_admin_password: str = "hradmin123"
    hr_admin_email: str = "hr@bank.local"
    auto_seed_demo_employees: bool = True
    secret_key: str = Field(
        default="change-me-in-production",
        validation_alias=AliasChoices("APP_SECRET_KEY", "SECRET_KEY"),
    )
    algorithm: str = "HS256"
    access_token_ttl_seconds: int = Field(default=28800, validation_alias="ACCESS_TOKEN_TTL_SECONDS")
    late_penalty_amount: float = 5.00
    face_storage_dir: Path = Path("storage/faces")
    attendance_storage_dir: Path = Path("storage/attendance")
    payslip_storage_dir: Path = Path("storage/payslips")
    templates_dir: Path = Path("app/templates")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
