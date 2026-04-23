# Attendance Face Detection Backend (FastAPI + Computer Vision)

This repository is the backend and public-user interface for a face-recognition attendance system. It handles model inference, real-time video streaming, attendance logging, and admin data APIs used by the separate Next.js admin portal.

## Abstract

The system applies a practical face-recognition workflow for attendance in educational or workplace settings. A webcam stream is processed in real time using facial landmarks and a trained classifier. Recognized users are logged to daily attendance files, while duplicate logs are suppressed within a 2-minute window to keep records clean.

## Table of Contents

- Introduction
- Literature Review
- Methodology
- Results
- Discussion
- Conclusion
- System Architecture
- Installation and Setup
- Running the System
- API Endpoints
- Project Structure
- Troubleshooting

## Introduction

Manual attendance processes are slow, error-prone, and difficult to audit in high-volume environments. This project introduces an automated attendance backend that combines real-time computer vision and web APIs.

Core objectives:
- Detect and recognize faces from a live webcam feed.
- Log attendance automatically in a structured format.
- Serve a simple public page for check-in/check-out interaction.
- Expose clean API endpoints for an external admin dashboard.

## Literature Review

Modern face-recognition attendance systems are usually built on three pillars:

1. Facial representation learning:
Classic methods (e.g., Eigenfaces/Fisherfaces) were lightweight but sensitive to pose and lighting. Deep learning methods significantly improved robustness.

2. Landmark-based geometric understanding:
Landmark detectors improve stability for non-frontal faces and support feature engineering from key facial points.

3. Operational logging and web integration:
Practical systems require not only recognition accuracy but also repeat suppression, API integration, and maintainable user/admin interfaces.

This project follows a hybrid practical approach using MediaPipe landmarks + TensorFlow classifier + FastAPI service architecture.

## Methodology

### 1. Data Collection

The dataset is collected using guided pose zones via `src/collect.py`:
- Front, left, right, up, down, near, far
- Automatic augmentation for brightness, blur, and mirroring

### 2. Feature Extraction

`src/extract.py` extracts:
- Landmark coordinates
- Geometric distances
- Pose-related angular signals

### 3. Model Training

`src/train.py` performs:
- Label encoding
- Feature scaling (`StandardScaler`)
- Neural network training with regularization and callbacks

### 4. Inference and Logging

`services/face_service.py` manages:
- Real-time frame processing
- Prediction smoothing via rolling buffer
- Confidence threshold filtering
- Attendance write action through `services/attendance_service.py`

Duplicate suppression policy:
- Same person is not re-logged within 120 seconds (minimum enforced in code).

### 5. Public and Admin Access

- Public page (`/`) is Jinja2-rendered for user interaction.
- Admin data is exposed through JSON APIs under `/api/admin/*`.

## Results

Current implementation provides:
- Real-time face detection/recognition stream at `/stream`.
- Public first-step action UX (Check In / Check Out) before starting detection.
- Attendance logs by date in CSV format.
- Admin-compatible API endpoints for dashboard, persons, and attendance history.
- Duplicate event suppression (2-minute window) for timeline clarity.

Artifacts produced after training:
- `models/face_model.h5`
- `models/label_encoder.pkl`
- `models/scaler.pkl`
- `models/landmarks_data.pkl`

## Discussion

Strengths:
- Clear separation between backend inference and admin frontend.
- Practical, reproducible training pipeline.
- Low operational overhead with CSV-based logging.

Limitations:
- No long-term database persistence by default for attendance records.
- Accuracy depends on dataset quality, lighting, and camera placement.
- Single-camera/single-feed assumptions in current deployment pattern.

Future enhancements:
- Add database-backed attendance records.
- Add anti-spoofing/liveness checks.
- Add multi-camera and role-based access control.

## Conclusion

This backend demonstrates a deployable and maintainable face-attendance pipeline that balances model practicality, system simplicity, and integration readiness. It is suitable as a final-year project foundation and can be extended into production-grade architecture with database and security upgrades.

## System Architecture

- Backend/API app: `attendance-face-detection`
- Admin frontend app: `attendance-face-detection-admin`

Exposed backend interfaces:
- Public page: `/`
- Stream endpoint: `/stream`
- Admin APIs: `/api/admin/*`

## Installation and Setup

Prerequisites:
- Python 3.10+
- Webcam device
- OS camera permissions enabled

Install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

First-time model asset setup:

```bash
python setup.py
```

## Running the System

### Training Pipeline

```bash
python src/collect.py
python src/extract.py
python src/train.py
```

### Start FastAPI Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8168
```

### URLs

- Public page: `http://127.0.0.1:8168/`
- Stream: `http://127.0.0.1:8168/stream`
- API docs: `http://127.0.0.1:8168/docs`

## API Endpoints

- `/api/admin/dashboard/summary`
- `/api/admin/attendance/records?date=YYYY-MM-DD`
- `/api/admin/attendance/dates`
- `/api/admin/persons/list`
- `/api/admin/persons/stats`

## Project Structure

- `routes/` API and page routes
- `services/` face pipeline and attendance logic
- `schemas/` Pydantic response models
- `src/` collection, extraction, training scripts
- `templates/` public page template
- `static/` frontend assets for public page
- `models/` trained model and preprocess artifacts
- `dataset/` captured face images
- `logs/` attendance CSV output

## Environment Variables

Main variables in `.env`:
- `CONFIDENCE_THRESHOLD`
- `RECOGNITION_COOLDOWN` (minimum enforced: 120)
- `BUFFER_SIZE`
- `WEBCAM_INDEX`
- `FRAME_WIDTH`, `FRAME_HEIGHT`
- `HOST`, `PORT`
- `ADMIN_ORIGIN`

## Troubleshooting

- Model not ready:
  - Run `python src/train.py`
  - Restart server
- No detections:
  - Check lighting and camera angle
  - Verify `WEBCAM_INDEX`
- Admin CORS issue:
  - Set `ADMIN_ORIGIN=http://localhost:3000`
