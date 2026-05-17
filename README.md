# Payroll Management System with Face Attendance

Internal FastAPI payroll platform backed by async SQLAlchemy and PostgreSQL. It supports employee onboarding with face registration, attendance clock-in/out using camera images, leave management, payroll runs, approval, and PDF payslip generation.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy 2.0 async + Alembic
- PostgreSQL (`asyncpg`)
- OpenCV + MediaPipe + TensorFlow face embeddings
- JWT auth (`python-jose`) + password hashing (`passlib`)
- Jinja2 templates
- ReportLab PDF payslips
- `python-dotenv`

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # optional, or export DATABASE_URL/SECRET_KEY
alembic upgrade head
python scripts/seed_payroll.py
uvicorn app.main:app --reload
```

Default seeded login:

- Username: `admin`
- Password: `admin123`

## Key API flows

- `POST /employees` accepts multipart employee fields plus `face_image`; face quality is validated before an employee/user is committed.
- `POST /attendance/clock-in` and `POST /attendance/clock-out` identify the employee from the uploaded camera image.
- `POST /payroll/run?month=&year=` creates a payroll run from attendance, overtime, late deductions, and unpaid leave.
- `PUT /payroll/{id}/approve` is admin-only.
- `GET /payroll/{id}/payslip/{employee_id}` generates and returns a PDF payslip.

All JSON API endpoints use the envelope:

```json
{ "success": true, "data": {}, "message": "OK" }
```
