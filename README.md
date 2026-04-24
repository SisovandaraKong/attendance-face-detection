# Banking Staff Attendance System Backend

FastAPI backend and public kiosk interface for a final-year thesis project on AI/computer vision for bank staff attendance management.

## Abstract

This project investigates how face recognition can be applied to bank staff attendance in a way that is technically meaningful for academic defense and operationally credible for administrative use. The backend combines FastAPI, MediaPipe landmark extraction, TensorFlow-based face classification, relational database persistence, lightweight liveness verification, and role-protected administrative APIs. A key design decision in this system is the separation between raw AI recognition events and final business attendance records. This allows the thesis to present not only recognition accuracy, but also how biometric evidence is translated into shift-aware attendance decisions with duplicate suppression, working-hour rules, and auditability.

## Problem Statement

Banks require attendance processes that are timely, traceable, and resistant to common operational issues such as proxy attendance, duplicate logging, and manual inconsistency. Traditional attendance approaches based on paper, spreadsheets, or basic timestamp capture offer limited verification of physical presence. At the same time, a realistic thesis project must avoid overengineering and remain implementable within student project constraints.

This project addresses that gap by designing and implementing a banking-oriented staff attendance backend that:

- uses computer vision as the main project identity
- stores operational data in a relational database instead of CSV as the primary system of record
- distinguishes between recognition evidence and official attendance outcomes
- applies lightweight liveness checking to reduce simple spoofing risk
- exposes protected APIs for a separate administrative frontend

## Objectives

The thesis objectives implemented in this repository are:

- build a FastAPI-based backend for realtime face-recognition attendance
- support a public kiosk-style check-in/check-out flow using Jinja2 and webcam streaming
- design a database-centered attendance pipeline suitable for bank staff operations
- separate raw recognition events from final attendance records
- implement basic but credible attendance rules:
  - check-in/check-out windows
  - grace period for lateness
  - duplicate prevention
  - outside-shift rejection
- add lightweight landmark-based liveness checking using blink and head movement cues
- provide protected admin APIs with role boundaries for `super_admin` and `hr_admin`

## Banking Context

The system is implemented and documented as a banking staff attendance platform rather than a generic classroom or workplace demo. The current domain model includes:

- branches
- departments
- employees
- shifts
- employee shift assignments
- kiosk devices
- recognition events
- attendance records
- attendance adjustments
- audit logs
- system users

The current seeded example models one bank office shift at headquarters, but the schema is intentionally broader to support thesis discussion around branch-based operations and future payroll integration.

## Current Scope

Implemented in this repository:

- FastAPI application and router structure
- Jinja2 public kiosk page
- MJPEG webcam streaming
- MediaPipe landmark-based feature extraction pipeline
- TensorFlow/Keras face recognition inference
- database-backed recognition event logging
- database-backed attendance records
- shift-aware business attendance processing
- duplicate scan suppression
- lightweight liveness verification
- protected admin APIs
- CSV export as optional reporting output

Not implemented as full production features:

- enterprise-grade anti-spoofing / PAD
- refresh-token session lifecycle
- full attendance adjustment approval workflow UI
- multi-branch role scoping
- payroll integration

## Methodology

### 1. Data Collection

Dataset collection is performed through guided capture using pose zones such as front, left, right, up, down, near, and far. Augmentation is applied to improve robustness under simple operational variation.

Relevant scripts:

- `src/collect.py`
- `src/extract.py`

### 2. Feature Engineering and Training

The AI pipeline uses MediaPipe facial landmarks and geometric face-derived features rather than a heavy end-to-end recognition stack. Features are scaled and then passed to a TensorFlow/Keras classifier.

Relevant scripts:

- `src/extract.py`
- `src/train.py`

Produced artifacts:

- `models/face_model.h5`
- `models/label_encoder.pkl`
- `models/scaler.pkl`
- `models/face_landmarker.task`

### 3. Realtime Inference

The backend loads the recognition model and MediaPipe detector at application startup through a singleton-style `FaceService`. Each frame is enhanced, processed for landmarks, transformed into recognition features, smoothed through a rolling prediction buffer, and then evaluated against confidence and liveness constraints.

Relevant implementation:

- `services/face_service.py`

### 4. Lightweight Liveness Detection

The project implements a lightweight, academically defensible liveness layer using facial landmarks that are already available from the MediaPipe pipeline. The current method combines:

- blink detection through eye aspect ratio
- small head movement through normalized nose-position change

This method is intentionally lightweight and suitable for thesis scope. It helps reduce simple static-photo spoofing risk, but it is not positioned as a production-grade presentation attack detection system.

Relevant implementation:

- `utils/liveness.py`
- `services/face_service.py`

### 5. Attendance Business Logic

The system does not directly convert every recognition into attendance. Instead:

1. a recognition event is written first
2. business rules evaluate whether the event is valid
3. only accepted events create or update attendance records

Implemented business rules include:

- duplicate suppression
- shift-based check-in window
- minimum checkout constraints
- grace period for lateness
- outside-working-hours rejection
- check-in vs check-out handling

Relevant implementation:

- `services/attendance_service.py`

### 6. Protected Administrative Access

Admin APIs are protected through a simple role-based token mechanism designed for thesis realism without introducing an external identity provider.

Current roles:

- `super_admin`
- `hr_admin`

Relevant implementation:

- `routes/auth.py`
- `services/auth_service.py`
- `dependencies/auth.py`

## System Architecture

This project is part of a two-repository architecture:

- `attendance-face-detection`: FastAPI backend and public kiosk flow
- `attendance-face-detection-admin`: Next.js admin portal

### Backend Responsibilities

This repository is responsible for:

- public kiosk page rendering
- webcam stream serving
- face recognition inference
- liveness verification
- recognition event storage
- attendance business processing
- protected admin APIs
- relational data management

### Architecture Flow

```mermaid
flowchart LR
    Camera[Webcam / Kiosk Camera] --> Stream[FastAPI Stream + FaceService]
    Stream --> CV[MediaPipe Landmarks + TensorFlow Classifier]
    CV --> Live[Liveness Check]
    CV --> Events[Recognition Events]
    Live --> Events
    Events --> Rules[Attendance Business Rules]
    Rules --> Records[Attendance Records]
    Records --> API[Protected Admin APIs]
    Events --> API
    API --> Admin[Next.js Admin Portal]
    Stream --> Public[Jinja2 Public Kiosk Page]
```

## Recognition Events vs Attendance Records

One of the main thesis-level architectural improvements in this system is the explicit separation between AI evidence and business attendance.

### Recognition Events

Recognition events represent raw AI inference output. They store information such as:

- timestamp
- predicted employee label
- confidence score
- liveness score
- event mode
- outcome such as `MATCHED`, `UNREGISTERED`, `DUPLICATE_IGNORED`, `OUTSIDE_SHIFT_WINDOW`, `LOW_LIVENESS`

These records are useful for:

- AI monitoring
- operational review
- error analysis
- thesis evidence

### Attendance Records

Attendance records represent official business interpretation. They store information such as:

- work date
- check-in time
- check-out time
- attendance status
- late minutes
- overtime minutes
- record state

These records are used for:

- daily attendance reporting
- HR review
- future payroll-oriented extensions

## Database-Centered Design

The project no longer treats CSV as the primary attendance store. The relational database is now the main system of record for:

- employees
- recognition events
- attendance records
- enrollment state
- shifts
- users and roles
- audit logs

CSV remains only for optional export or legacy fallback scenarios.

## Mermaid ERD

```mermaid
erDiagram
    BRANCHES ||--o{ DEPARTMENTS : has
    BRANCHES ||--o{ EMPLOYEES : has
    BRANCHES ||--o{ KIOSK_DEVICES : has

    DEPARTMENTS ||--o{ EMPLOYEES : groups
    DEPARTMENTS ||--o{ SYSTEM_USERS : scopes

    EMPLOYEES ||--o{ EMPLOYEE_SHIFT_ASSIGNMENTS : assigned
    SHIFTS ||--o{ EMPLOYEE_SHIFT_ASSIGNMENTS : defines

    EMPLOYEES ||--o{ FACE_PROFILES : owns
    EMPLOYEES ||--o{ ENROLLMENT_SESSIONS : enrolls
    ENROLLMENT_SESSIONS ||--o{ ENROLLMENT_SAMPLES : contains

    EMPLOYEES ||--o{ RECOGNITION_EVENTS : may_match
    FACE_PROFILES ||--o{ RECOGNITION_EVENTS : used_by
    KIOSK_DEVICES ||--o{ RECOGNITION_EVENTS : captures

    EMPLOYEES ||--o{ ATTENDANCE_RECORDS : has
    SHIFTS ||--o{ ATTENDANCE_RECORDS : applies_to
    RECOGNITION_EVENTS ||--o| ATTENDANCE_RECORDS : checkin_event
    RECOGNITION_EVENTS ||--o| ATTENDANCE_RECORDS : checkout_event

    ATTENDANCE_RECORDS ||--o{ ATTENDANCE_ADJUSTMENTS : adjusted_by
    SYSTEM_USERS ||--o{ ATTENDANCE_ADJUSTMENTS : requests
    SYSTEM_USERS ||--o{ AUDIT_LOGS : acts

    BRANCHES {
        bigint id PK
        varchar code UK
        varchar name
    }

    DEPARTMENTS {
        bigint id PK
        bigint branch_id FK
        varchar code
        varchar name
    }

    EMPLOYEES {
        bigint id PK
        varchar employee_code UK
        bigint branch_id FK
        bigint department_id FK
        varchar full_name
        varchar employment_status
        varchar face_enrollment_status
    }

    SHIFTS {
        bigint id PK
        varchar code UK
        time start_time
        time end_time
        integer grace_minutes
        integer late_after_minutes
    }

    SYSTEM_USERS {
        bigint id PK
        varchar username UK
        varchar role
        boolean is_active
    }

    KIOSK_DEVICES {
        bigint id PK
        bigint branch_id FK
        varchar device_code UK
        varchar device_name
    }

    FACE_PROFILES {
        bigint id PK
        bigint employee_id FK
        integer profile_version
        varchar model_name
        text artifact_uri
    }

    ENROLLMENT_SESSIONS {
        bigint id PK
        bigint employee_id FK
        varchar session_status
        integer accepted_samples
    }

    ENROLLMENT_SAMPLES {
        bigint id PK
        bigint enrollment_session_id FK
        bigint employee_id FK
        text file_uri UK
        boolean is_accepted
    }

    RECOGNITION_EVENTS {
        bigint id PK
        timestamptz occurred_at
        bigint employee_id FK
        bigint kiosk_device_id FK
        numeric confidence
        numeric liveness_score
        varchar event_mode
        varchar match_result
    }

    ATTENDANCE_RECORDS {
        bigint id PK
        bigint employee_id FK
        date work_date
        timestamptz check_in_time
        timestamptz check_out_time
        varchar attendance_status
        varchar record_state
    }

    ATTENDANCE_ADJUSTMENTS {
        bigint id PK
        bigint attendance_record_id FK
        varchar approval_status
    }

    AUDIT_LOGS {
        bigint id PK
        bigint actor_user_id FK
        varchar action
        varchar entity_type
    }
```

## Project Structure

- `main.py` application entry point
- `routes/` FastAPI routers
- `services/` inference and business logic
- `dependencies/` reusable auth dependencies
- `schemas/` Pydantic request/response models
- `database/` SQLAlchemy models, session, migrations, seeding
- `templates/` Jinja2 public kiosk pages
- `static/` public kiosk assets
- `src/` dataset collection, feature extraction, training scripts
- `models/` trained AI artifacts
- `dataset/` captured training images
- `logs/` legacy fallback / export-oriented files

## API Surface

### Public

- `/`
- `/stream`
- `/api/public/recent`
- `/api/public/status`

### Authentication

- `/api/auth/login`
- `/api/auth/me`
- `/api/auth/logout`

### Admin

- `/api/admin/dashboard/summary`
- `/api/admin/attendance/records`
- `/api/admin/attendance/dates`
- `/api/admin/attendance/export.csv`
- `/api/admin/persons`
- `/api/admin/persons/list`
- `/api/admin/persons/stats`
- `/api/admin/recognition-events`
- `/api/admin/recognition-events/stats`
- `/api/admin/reports/summary`
- `/api/admin/master-data/branches`
- `/api/admin/master-data/shifts`
- `/api/admin/system/health`

## Installation and Setup

### Prerequisites

- Python 3.10+
- PostgreSQL
- webcam device
- camera permissions enabled

### Environment Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Database Setup

```bash
docker compose -f postgres/docker-compose.yml up -d
psql postgresql://attendance:attendance@localhost:5168/attendance -f database/migrations/0001_initial_schema.sql
psql postgresql://attendance:attendance@localhost:5168/attendance -f database/migrations/0002_seed_baseline.sql
```

### Model Asset Setup

```bash
python setup.py
```

## Running the Backend

### Training Pipeline

```bash
python src/collect.py
python src/extract.py
python src/train.py
```

### Start Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8168
```

### Default URLs

- public kiosk: `http://127.0.0.1:8168/`
- stream: `http://127.0.0.1:8168/stream`
- OpenAPI docs: `http://127.0.0.1:8168/docs`

## Environment Variables

Important variables in `.env` include:

- `DATABASE_URL`
- `CONFIDENCE_THRESHOLD`
- `RECOGNITION_COOLDOWN`
- `EVENT_EMIT_DEBOUNCE_SECONDS`
- `CHECKIN_WINDOW_BEFORE_SHIFT_MINUTES`
- `CHECKIN_WINDOW_AFTER_SHIFT_MINUTES`
- `CHECKOUT_WINDOW_BEFORE_SHIFT_MINUTES`
- `CHECKOUT_WINDOW_AFTER_SHIFT_MINUTES`
- `MIN_CHECKOUT_BEFORE_END_MINUTES`
- `LIVENESS_REQUIRED`
- `LIVENESS_BLINK_EAR_THRESHOLD`
- `LIVENESS_BLINK_MIN_CLOSED_FRAMES`
- `LIVENESS_HEAD_MOVEMENT_THRESHOLD`
- `LIVENESS_WINDOW_SECONDS`
- `LIVENESS_MIN_STABLE_FRAMES`
- `LIVENESS_PASS_SCORE`
- `ADMIN_ORIGIN`
- `APP_SECRET_KEY`
- `ACCESS_TOKEN_TTL_SECONDS`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `HR_ADMIN_USERNAME`, `HR_ADMIN_PASSWORD`

## Role-Permission Matrix

| Area | super_admin | hr_admin |
|---|---|---|
| Login to admin portal | Yes | Yes |
| Dashboard, attendance, reports | Yes | Yes |
| Recognition event review | Yes | Yes |
| Employee registration and update | Yes | Yes |
| Branch and shift reference data | Yes | Yes |
| System-only monitoring page | Yes | No |

## Limitations

The current implementation is intentionally thesis-scoped. Important limitations include:

- recognition accuracy depends on data quality, lighting, and camera positioning
- the liveness layer is lightweight and not a substitute for industrial anti-spoofing
- the deployment model currently assumes a single active kiosk camera per backend process
- role enforcement is basic and does not yet include fine-grained field-level or branch-level restrictions
- payroll integration is future-facing rather than implemented

## Future Work

Reasonable extensions after this thesis include:

- stronger anti-spoofing / presentation attack detection
- role-scoped branch administration
- attendance adjustment and approval workflow completion
- Alembic-based incremental migrations beyond the current SQL migration approach
- payroll and leave integration
- multi-kiosk orchestration and device health management

## Troubleshooting

- Model not ready:
  - run `python src/train.py`
  - restart the FastAPI server
- No detections:
  - check lighting, camera framing, and `WEBCAM_INDEX`
- Database connection issues:
  - verify `DATABASE_URL`
  - verify PostgreSQL container is running
- Admin login issues:
  - verify seeded `super_admin` / `hr_admin` credentials in `.env`
  - verify `APP_SECRET_KEY` is set consistently
