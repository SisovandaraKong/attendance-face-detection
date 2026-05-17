BEGIN;

/*
0003_payroll_schema.sql
Adds payroll master/configuration tables and monthly payroll records for the
attendance-backed banking staff payroll workflow. The migration creates:
  - salary_configs
  - deduction_rules
  - payroll_records
It also enforces one payroll record per employee per month/year period.
*/

CREATE TABLE IF NOT EXISTS salary_configs (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    effective_from DATE NOT NULL,
    base_salary NUMERIC(12,2) NOT NULL,
    overtime_rate_multiplier NUMERIC(5,2) NOT NULL DEFAULT 1.5,
    transport_allowance NUMERIC(12,2) NOT NULL DEFAULT 0,
    meal_allowance NUMERIC(12,2) NOT NULL DEFAULT 0,
    grade VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS deduction_rules (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    rule_type VARCHAR(20) NOT NULL,
    value NUMERIC(12,2) NOT NULL,
    applies_to_grade VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS payroll_records (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    working_days_in_period INTEGER NOT NULL,
    days_present INTEGER NOT NULL,
    days_absent INTEGER NOT NULL,
    days_late INTEGER NOT NULL,
    total_late_minutes INTEGER NOT NULL DEFAULT 0,
    total_overtime_minutes INTEGER NOT NULL DEFAULT 0,
    base_salary NUMERIC(12,2) NOT NULL,
    transport_allowance NUMERIC(12,2) NOT NULL DEFAULT 0,
    meal_allowance NUMERIC(12,2) NOT NULL DEFAULT 0,
    overtime_pay NUMERIC(12,2) NOT NULL DEFAULT 0,
    gross_pay NUMERIC(12,2) NOT NULL,
    deductions_json JSON NOT NULL,
    total_deductions NUMERIC(12,2) NOT NULL DEFAULT 0,
    net_pay NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    approved_by BIGINT REFERENCES system_users(id),
    approved_at TIMESTAMPTZ,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_payroll_employee_period UNIQUE (employee_id, period_month, period_year)
);

COMMIT;
