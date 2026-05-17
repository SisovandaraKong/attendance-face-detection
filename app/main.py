"""FastAPI application entry point for the payroll management system."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.database import AsyncSessionLocal, init_db
from app.routes import analytics, attendance, auth, dashboard, employees, leaves, payroll, portal, reports
from app.services.bootstrap_service import ensure_bootstrap_data


settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    async with AsyncSessionLocal() as db:
        await ensure_bootstrap_data(db)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Internal payroll, attendance, leave, and face recognition management API.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.admin_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(leaves.router)
app.include_router(payroll.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(portal.router)
app.include_router(analytics.router)


@app.get("/health")
async def health() -> dict:
    return {"success": True, "data": {"status": "ok"}, "message": "Service healthy"}


@app.get("/")
async def public_attendance(request: Request):
    """Public-facing daily face attendance page (clock-in / clock-out)."""
    return templates.TemplateResponse(request, "attendance.html")


@app.get("/dashboard")
async def admin_dashboard(request: Request):
    """Admin/HR dashboard for employee, leave, payroll management."""
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/portal")
async def employee_portal(request: Request):
    """Employee Self-Service portal for viewing payslips, attendance, and leaves."""
    return templates.TemplateResponse(request, "portal.html")

