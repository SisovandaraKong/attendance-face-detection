"""
utils/logger.py
────────────────────────────────────────────────────────────
Attendance logging — saves records to a CSV per day.
────────────────────────────────────────────────────────────
"""

import os
import csv
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

LOGS_DIR = os.getenv("LOGS_DIR", "./logs")


def log_attendance(name: str) -> str:
    """
    Write an attendance entry for `name` with current timestamp.
    Returns the log file path.
    Skips duplicate entries within the same day.
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    today    = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOGS_DIR, f"attendance_{today}.csv")

    # Read existing entries for today
    existing = set()
    if os.path.exists(log_file):
        with open(log_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add(row.get("Name", ""))

    # Write header if new file
    write_header = not os.path.exists(log_file)
    with open(log_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Name", "Date", "Time", "Status"])
        if write_header:
            writer.writeheader()
        writer.writerow({
            "Name":   name.replace("_", " "),
            "Date":   today,
            "Time":   datetime.now().strftime("%H:%M:%S"),
            "Status": "Present",
        })

    return log_file


def get_today_log() -> list[dict]:
    """Return list of attendance records for today."""
    today    = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOGS_DIR, f"attendance_{today}.csv")
    if not os.path.exists(log_file):
        return []
    with open(log_file, "r", newline="") as f:
        return list(csv.DictReader(f))