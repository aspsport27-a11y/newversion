-- ============================================
-- Migration 012 — Beban Holding / Owner (Fase 1 RBAC/laporan)
-- Pengeluaran level holding yang SENSITIF & HANYA HO/Admin yang boleh lihat:
-- prive, fee direktur, bonus, dll. Keluar dari rekening holding (treasury),
-- TIDAK menyentuh venue mana pun → tak pernah muncul di Laporan Bisnis venue,
-- hanya di Laporan Manajemen.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS holding_expenses (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) UNIQUE NOT NULL,
    category VARCHAR(40) NOT NULL,            -- Prive | Fee Direktur | Bonus | Lainnya
    description VARCHAR(200),
    amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
    source_account_id INTEGER REFERENCES bank_accounts(id),  -- rekening holding sumber dana
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_holding_expenses_date ON holding_expenses(expense_date);

COMMIT;
