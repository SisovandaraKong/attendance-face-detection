"""
schemas/attendance.py
─────────────────────────────────────────────────────────────
Pydantic models for all request / response payloads.

Every API response follows the same envelope:
  { "success": bool, "data": ..., "message": str }
─────────────────────────────────────────────────────────────
"""

from datetime import date, time as dt_time
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ── Generic response envelope ────────────────────────────────
class APIResponse(BaseModel):
    success: bool
    data: Any = None
    message: str = ""


# ── Attendance record ────────────────────────────────────────
class AttendanceRecord(BaseModel):
    name: str
    date: str          # "YYYY-MM-DD"
    time: str          # "HH:MM:SS"
    status: str = "Present"


class AttendanceListResponse(APIResponse):
    data: List[AttendanceRecord] = []


# ── Person management ────────────────────────────────────────
class PersonInfo(BaseModel):
    name: str                           # directory name (underscores)
    display_name: str                   # human-readable (spaces)
    image_count: int
    complete: bool                      # True if dataset is full


class PersonListResponse(APIResponse):
    data: List[PersonInfo] = []


# ── Prediction result (used internally + exposed to JS) ──────
class PredictionResult(BaseModel):
    label: str            # "Unknown" or person name (spaces)
    confidence: float     # 0.0 – 1.0
    recognised: bool      # True when confidence ≥ threshold
