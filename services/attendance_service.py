"""
services/attendance_service.py
─────────────────────────────────────────────────────────────
All CSV attendance log read/write logic lives here.

One CSV file per calendar day: logs/attendance_YYYY-MM-DD.csv
Columns: Name, Date, Time, Status
─────────────────────────────────────────────────────────────
"""

import csv
import os
from datetime import datetime
from typing import Dict, List, Optional

from schemas.attendance import AttendanceRecord

# ── Paths resolved relative to project root ─────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")

CSV_FIELDNAMES = ["Name", "Date", "Time", "Status"]

os.makedirs(LOGS_DIR, exist_ok=True)


def _log_path(date_str: str) -> str:
    """Return the absolute path to the log file for a given date string."""
    return os.path.join(LOGS_DIR, f"attendance_{date_str}.csv")


def read_log(date_str: Optional[str] = None) -> List[AttendanceRecord]:
    """
    Read attendance records for a single day.

    Parameters
    ----------
    date_str : "YYYY-MM-DD" — defaults to today if omitted

    Returns
    -------
    List of AttendanceRecord (empty list if file does not exist yet)
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    path = _log_path(date_str)
    if not os.path.exists(path):
        return []

    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [
                AttendanceRecord(
                    name=row.get("Name", ""),
                    date=row.get("Date", date_str),
                    time=row.get("Time", ""),
                    status=row.get("Status", "Present"),
                )
                for row in reader
            ]
    except Exception as exc:
        raise RuntimeError(f"Failed to read log for {date_str}: {exc}") from exc


def write_record(name: str) -> AttendanceRecord:
    """
    Append one Present record for *name* to today's log.

    Parameters
    ----------
    name : directory-style name (underscores) — stored with spaces

    Returns
    -------
    The AttendanceRecord that was written
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now   = datetime.now().strftime("%H:%M:%S")
    path  = _log_path(today)

    record = AttendanceRecord(
        name=name.replace("_", " "),
        date=today,
        time=now,
        status="Present",
    )

    write_header = not os.path.exists(path)
    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "Name":   record.name,
                "Date":   record.date,
                "Time":   record.time,
                "Status": record.status,
            })
    except Exception as exc:
        raise RuntimeError(f"Failed to write attendance for {name}: {exc}") from exc

    return record


def list_log_dates() -> List[str]:
    """
    Return all dates that have a log file, sorted newest-first.
    """
    try:
        files = [
            f for f in os.listdir(LOGS_DIR)
            if f.startswith("attendance_") and f.endswith(".csv")
        ]
        dates = [f[len("attendance_"):-len(".csv")] for f in files]
        return sorted(dates, reverse=True)
    except Exception:
        return []


def get_summary() -> Dict[str, int]:
    """
    Return a dict mapping date → present count for all log files.
    Useful for the dashboard weekly summary chart.
    """
    summary: Dict[str, int] = {}
    for date_str in list_log_dates():
        records = read_log(date_str)
        summary[date_str] = len(records)
    return summary
