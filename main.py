"""
main.py — FastAPI application entry point.

Responsibilities (only):
  • Create the FastAPI app instance
  • Register all routers
  • Mount static files and configure Jinja2 templates
  • Load / unload the FaceService via lifespan context manager
  • No business logic lives here
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from routes import attendance, dashboard, persons, stream
from services.face_service import FaceService

# ── Load .env before anything reads os.getenv ───────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ── Lifespan — load heavy resources once, release on shutdown ─
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up — loading FaceService…")
    app.state.face_service = FaceService()
    if app.state.face_service.is_ready:
        logger.info("FaceService loaded successfully.")
    else:
        logger.warning(
            "FaceService NOT ready — run src/train.py first. "
            "The UI will still work but the live feed will show no predictions."
        )
    yield
    logger.info("Shutting down — releasing FaceService resources…")
    app.state.face_service.close()


# ── App factory ───────────────────────────────────────────────
app = FastAPI(
    title="Face Recognition Attendance System",
    description="Automated attendance via MediaPipe + TensorFlow face recognition.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Static files & templates ──────────────────────────────────
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(dashboard.router)
app.include_router(stream.router)
app.include_router(attendance.router)
app.include_router(persons.router)
