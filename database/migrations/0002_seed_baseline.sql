BEGIN;

INSERT INTO branches (code, name, city, is_active)
VALUES ('HQ', 'Headquarters', 'Phnom Penh', TRUE)
ON CONFLICT (code) DO NOTHING;

INSERT INTO departments (branch_id, code, name, is_active)
SELECT b.id, 'OPS', 'Operations', TRUE
FROM branches b
WHERE b.code = 'HQ'
ON CONFLICT ON CONSTRAINT uq_departments_branch_code DO NOTHING;

INSERT INTO shifts (
    code,
    name,
    start_time,
    end_time,
    grace_minutes,
    late_after_minutes,
    min_checkout_time,
    is_overnight,
    is_active
)
VALUES (
    'GENERAL',
    'General Shift',
    '08:00:00',
    '17:00:00',
    10,
    10,
    '16:00:00',
    FALSE,
    TRUE
)
ON CONFLICT (code) DO NOTHING;

COMMIT;
