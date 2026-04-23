# Attendance Face Detection (FastAPI + ML)

This project is the face-recognition backend and public check-in page.

It provides:
- Live face detection and recognition stream
- Attendance logging to daily CSV files
- Admin APIs consumed by the Next.js admin portal
- Public Jinja2 page for face check-in only

## Project Role in Fullstack Architecture

- Backend/API app: `attendance-face-detection`
- Admin frontend app: `attendance-face-detection-admin`

This backend serves:
- Public page at `/`
- MJPEG stream at `/stream`
- Admin JSON APIs at `/api/admin/*`

## Tech Stack

- FastAPI
- MediaPipe Face Landmarker
- TensorFlow / Keras
- OpenCV
- scikit-learn
- Jinja2 (public page only)

## Key Folders

- `routes/` API and page routes
- `services/` face pipeline and attendance logic
- `schemas/` Pydantic response models
- `src/` data collection, extraction, and training scripts
- `templates/` public page template
- `static/` public page assets
- `models/` ML assets (`.task`, `.h5`, encoder, scaler)
- `dataset/` collected face images
- `logs/` daily attendance CSV files

## Prerequisites

- Python 3.10+
- Webcam device
- OS camera permissions enabled

## Installation

1. Create and activate a virtual environment.
2. Install dependencies.
3. Copy env file.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Environment Variables

Use `.env` (from `.env.example`):

- `CONFIDENCE_THRESHOLD` recognition confidence threshold
- `RECOGNITION_COOLDOWN` minimum seconds before re-logging same person
- `BUFFER_SIZE` rolling prediction buffer size
- `WEBCAM_INDEX` webcam index
- `FRAME_WIDTH`, `FRAME_HEIGHT` capture size
- `HOST`, `PORT` FastAPI server host/port
- `ADMIN_ORIGIN` CORS origin for Next.js admin

## First-Time Model Setup

Run once to download MediaPipe model:

```bash
python setup.py
```

## Data and Training Pipeline

1. Collect images by guided pose zones:

```bash
python src/collect.py
```

2. Extract facial landmark features:

```bash
python src/extract.py
```

3. Train classifier model:

```bash
python src/train.py
```

Generated artifacts:
- `models/face_model.h5`
- `models/label_encoder.pkl`
- `models/scaler.pkl`
- `models/landmarks_data.pkl`

## Run Backend

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8168
```

## URLs

- Public face check-in page: `http://127.0.0.1:8168/`
- Stream endpoint: `http://127.0.0.1:8168/stream`
- API docs: `http://127.0.0.1:8168/docs`

## Admin API Endpoints

- `/api/admin/dashboard/summary`
- `/api/admin/attendance/records?date=YYYY-MM-DD`
- `/api/admin/attendance/dates`
- `/api/admin/persons/list`
- `/api/admin/persons/stats`

## Integration with Next.js Admin

Set backend CORS origin in `.env`:

```env
ADMIN_ORIGIN=http://localhost:3000
```

Then run the admin project separately and point it to this API.

## Troubleshooting

- Model not ready in UI:
  - Run `python src/train.py`
  - Restart FastAPI server
- No face detected:
  - Ensure webcam index is correct (`WEBCAM_INDEX`)
  - Improve lighting / camera distance
- CORS errors in admin app:
  - Ensure `ADMIN_ORIGIN` matches your admin URL
