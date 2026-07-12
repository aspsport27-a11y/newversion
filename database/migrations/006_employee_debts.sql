-- ============================================
-- Migration 006 — piutang/kasbon karyawan
-- type: advance (kasbon keluar → nambah utang) | repayment (potong gaji/bayar → kurangi utang)
-- Saldo piutang = SUM(advance) - SUM(repayment). Dipotong saat payroll (modul nanti).
-- Tabel employees & users.employee_id sudah ada dari schema awal.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS employee_debts (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    type VARCHAR(10) NOT NULL,              -- advance | repayment
    amount DECIMAL(15,2) NOT NULL,
    note VARCHAR(200),
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_employee_debts_emp ON employee_debts(employee_id);

COMMIT;
