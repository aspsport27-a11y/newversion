-- ============================================
-- Migration 021 — Lampiran Payroll + Rekonsiliasi Bank
-- 1) payroll_attachments: bukti transfer/dokumen pada payroll run (spt po_attachments).
-- 2) bank_reconciliations: bandingkan saldo sistem vs rekening koran per tanggal,
--    ADMIN ONLY (bukan RBAC configurable — hard restricted role='admin').
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS payroll_attachments (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    stored_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    size_bytes INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bank_reconciliations (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
    period_to DATE NOT NULL,
    statement_balance NUMERIC(15,2) NOT NULL,
    system_balance NUMERIC(15,2) NOT NULL,
    difference NUMERIC(15,2) NOT NULL DEFAULT 0,
    note TEXT,
    status VARCHAR(10) NOT NULL DEFAULT 'open',  -- open|resolved
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_by INTEGER REFERENCES users(id),
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bank_reconciliations_account ON bank_reconciliations(account_id);

COMMIT;
