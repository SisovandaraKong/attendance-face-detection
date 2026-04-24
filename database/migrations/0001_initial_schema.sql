BEGIN;

CREATE TABLE IF NOT EXISTS branches (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    city VARCHAR(80),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS departments (
    id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL REFERENCES branches(id),
    code VARCHAR(20) NOT NULL,
    name VARCHAR(120) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_departments_branch_code UNIQUE (branch_id, code),
    CONSTRAINT uq_departments_branch_name UNIQUE (branch_id, name)
);

CREATE TABLE IF NOT EXISTS employees (
    id BIGSERIAL PRIMARY KEY,
    employee_code VARCHAR(30) NOT NULL UNIQUE,
    branch_id BIGINT NOT NULL REFERENCES branches(id),
    department_id BIGINT NOT NULL REFERENCES departments(id),
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    full_name VARCHAR(180) NOT NULL,
    email VARCHAR(120) UNIQUE,
    phone VARCHAR(30),
    employment_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    join_date DATE,
    face_enrollment_status VARCHAR(20) NOT NULL DEFAULT 'NOT_ENROLLED',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shifts (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(80) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    grace_minutes INTEGER NOT NULL DEFAULT 10,
    late_after_minutes INTEGER NOT NULL DEFAULT 10,
    min_checkout_time TIME,
    is_overnight BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(60) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(120) UNIQUE,
    role VARCHAR(30) NOT NULL,
    branch_id BIGINT REFERENCES branches(id),
    department_id BIGINT REFERENCES departments(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employee_shift_assignments (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    shift_id BIGINT NOT NULL REFERENCES shifts(id),
    effective_from DATE NOT NULL,
    effective_to DATE,
    is_primary BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_by BIGINT REFERENCES system_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_employee_shift_effective UNIQUE (employee_id, shift_id, effective_from)
);

CREATE TABLE IF NOT EXISTS face_profiles (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    profile_version INTEGER NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(40),
    feature_dim INTEGER NOT NULL,
    artifact_uri TEXT NOT NULL,
    quality_score NUMERIC(5,2),
    sample_count INTEGER NOT NULL DEFAULT 0,
    profile_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    trained_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_face_profile_version UNIQUE (employee_id, profile_version)
);

CREATE TABLE IF NOT EXISTS enrollment_sessions (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    initiated_by BIGINT REFERENCES system_users(id),
    capture_device VARCHAR(80),
    required_samples INTEGER NOT NULL DEFAULT 1050,
    collected_samples INTEGER NOT NULL DEFAULT 0,
    accepted_samples INTEGER NOT NULL DEFAULT 0,
    rejected_samples INTEGER NOT NULL DEFAULT 0,
    session_status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS enrollment_samples (
    id BIGSERIAL PRIMARY KEY,
    enrollment_session_id BIGINT NOT NULL REFERENCES enrollment_sessions(id),
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    file_uri TEXT NOT NULL UNIQUE,
    zone_label VARCHAR(30) NOT NULL,
    augmentation_type VARCHAR(30),
    quality_score NUMERIC(5,2),
    is_accepted BOOLEAN NOT NULL DEFAULT TRUE,
    rejection_reason VARCHAR(200),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kiosk_devices (
    id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL REFERENCES branches(id),
    device_code VARCHAR(40) NOT NULL UNIQUE,
    device_name VARCHAR(80) NOT NULL,
    location_label VARCHAR(120),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recognition_events (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    kiosk_device_id BIGINT REFERENCES kiosk_devices(id),
    employee_id BIGINT REFERENCES employees(id),
    face_profile_id BIGINT REFERENCES face_profiles(id),
    predicted_label VARCHAR(180),
    confidence NUMERIC(6,5) NOT NULL,
    liveness_score NUMERIC(6,5),
    event_mode VARCHAR(20) NOT NULL DEFAULT 'CHECK_IN',
    match_result VARCHAR(30) NOT NULL DEFAULT 'MATCHED',
    quality_score NUMERIC(5,2),
    image_uri TEXT,
    metadata JSONB,
    is_consumed BOOLEAN NOT NULL DEFAULT FALSE,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    branch_id BIGINT NOT NULL REFERENCES branches(id),
    department_id BIGINT NOT NULL REFERENCES departments(id),
    work_date DATE NOT NULL,
    shift_id BIGINT REFERENCES shifts(id),
    check_in_time TIMESTAMPTZ,
    check_out_time TIMESTAMPTZ,
    check_in_event_id BIGINT REFERENCES recognition_events(id),
    check_out_event_id BIGINT REFERENCES recognition_events(id),
    attendance_status VARCHAR(30) NOT NULL DEFAULT 'PRESENT',
    minutes_late INTEGER NOT NULL DEFAULT 0,
    overtime_minutes INTEGER NOT NULL DEFAULT 0,
    source_type VARCHAR(20) NOT NULL DEFAULT 'AUTO',
    record_state VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    approved_by BIGINT REFERENCES system_users(id),
    approved_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_attendance_employee_work_date UNIQUE (employee_id, work_date)
);

CREATE TABLE IF NOT EXISTS attendance_adjustments (
    id BIGSERIAL PRIMARY KEY,
    attendance_record_id BIGINT NOT NULL REFERENCES attendance_records(id),
    requested_by BIGINT NOT NULL REFERENCES system_users(id),
    reviewed_by BIGINT REFERENCES system_users(id),
    adjustment_type VARCHAR(30) NOT NULL,
    old_values JSONB NOT NULL,
    new_values JSONB NOT NULL,
    reason TEXT NOT NULL,
    approval_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    review_note TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_user_id BIGINT REFERENCES system_users(id),
    action VARCHAR(120) NOT NULL,
    entity_type VARCHAR(60) NOT NULL,
    entity_id VARCHAR(60) NOT NULL,
    result VARCHAR(20) NOT NULL,
    reason TEXT,
    ip_address VARCHAR(50),
    user_agent TEXT,
    request_id VARCHAR(36),
    old_values JSONB,
    new_values JSONB,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS ix_recognition_events_occurred_at
    ON recognition_events (occurred_at);
CREATE INDEX IF NOT EXISTS ix_recognition_events_employee_occurred
    ON recognition_events (employee_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_recognition_events_kiosk_occurred
    ON recognition_events (kiosk_device_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_attendance_work_date_branch
    ON attendance_records (work_date, branch_id);
CREATE INDEX IF NOT EXISTS ix_attendance_work_date_department
    ON attendance_records (work_date, department_id);
CREATE INDEX IF NOT EXISTS ix_attendance_adjustments_record_status
    ON attendance_adjustments (attendance_record_id, approval_status);
CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_time
    ON audit_logs (actor_user_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_time
    ON audit_logs (entity_type, entity_id, occurred_at);

COMMIT;
