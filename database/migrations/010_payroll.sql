-- ============================================
-- Migration 010 — Payroll
-- Alur: Manager generate (draft) -> submit -> HO approve -> HO pay (transfer).
-- Saat PAID: cicilan kasbon dieksekusi (employee_debts repayment, kurangi saldo).
-- employees.allowance = tunjangan tetap/bulan.
-- Tabel lama `payroll` (schema awal) = DEPRECATED.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE employees ADD COLUMN IF NOT EXISTS allowance DECIMAL(15,2);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) UNIQUE NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    created_by INTEGER REFERENCES users(id),
    total_net DECIMAL(15,2) NOT NULL DEFAULT 0,
    notes TEXT,
    status VARCHAR(12) NOT NULL DEFAULT 'draft',  -- draft|submitted|approved|paid|rejected
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    paid_by INTEGER REFERENCES users(id),
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (venue_id, period_year, period_month)
);

CREATE TABLE IF NOT EXISTS payroll_items (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    employee_name VARCHAR(100) NOT NULL,
    position VARCHAR(100),
    base_salary DECIMAL(15,2) NOT NULL DEFAULT 0,
    allowance DECIMAL(15,2) NOT NULL DEFAULT 0,
    kasbon_deduction DECIMAL(15,2) NOT NULL DEFAULT 0,
    other_deduction DECIMAL(15,2) NOT NULL DEFAULT 0,
    net_salary DECIMAL(15,2) NOT NULL DEFAULT 0,
    bank_name VARCHAR(50),
    bank_account VARCHAR(50),
    note VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payroll_runs_venue ON payroll_runs(venue_id);
CREATE INDEX IF NOT EXISTS idx_payroll_items_run ON payroll_items(run_id);

COMMIT;
