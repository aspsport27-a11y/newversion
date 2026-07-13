-- ============================================
-- Migration 011 — Kas & Bank (Treasury)
-- Rekening (venue + holding) + buku besar mutasi + setoran cash + rekonsiliasi QRIS.
-- Aliran: QRIS->rek venue (HO approve vs bank), cash->setor ke holding (hari closing),
-- pengeluaran default holding, sapu venue->holding.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS bank_accounts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(10) NOT NULL DEFAULT 'venue',   -- venue | holding
    venue_id INTEGER REFERENCES venues(id) ON DELETE CASCADE,  -- NULL utk holding
    bank_name VARCHAR(50),
    account_number VARCHAR(50),
    opening_balance DECIMAL(15,2) NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Buku besar mutasi rekening. Saldo = opening_balance + SUM(in) - SUM(out).
CREATE TABLE IF NOT EXISTS account_transactions (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
    direction VARCHAR(3) NOT NULL,               -- in | out
    amount DECIMAL(15,2) NOT NULL,
    kind VARCHAR(16) NOT NULL,                    -- qris_in|cash_deposit|expense|transfer_in|transfer_out|adjustment
    ref_type VARCHAR(20),                         -- op_request|po|payroll|setoran|qris|sweep|manual
    ref_id INTEGER,
    tx_date DATE NOT NULL DEFAULT CURRENT_DATE,
    note VARCHAR(200),
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Setoran tunai (gabungan shift) ke holding
CREATE TABLE IF NOT EXISTS cash_deposits (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) UNIQUE NOT NULL,
    deposit_date DATE NOT NULL DEFAULT CURRENT_DATE,
    to_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
    expected_amount DECIMAL(15,2) NOT NULL DEFAULT 0,   -- dari deposit_amount shift
    counted_amount DECIMAL(15,2) NOT NULL DEFAULT 0,    -- hitung fisik HO
    variance DECIMAL(15,2) NOT NULL DEFAULT 0,
    note TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rekonsiliasi QRIS per venue (HO cocokkan POS vs bank)
CREATE TABLE IF NOT EXISTS qris_settlements (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    account_id INTEGER REFERENCES bank_accounts(id),
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,
    system_amount DECIMAL(15,2) NOT NULL DEFAULT 0,     -- total QRIS di POS
    actual_amount DECIMAL(15,2) NOT NULL DEFAULT 0,     -- yang masuk rek bank
    status VARCHAR(10) NOT NULL DEFAULT 'draft',        -- draft|approved
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tandai shift sudah masuk setoran (biar tak dobel)
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS deposit_id INTEGER REFERENCES cash_deposits(id);
-- Sumber dana pembayaran (rekening yang dipakai) pada modul pengeluaran
ALTER TABLE op_requests ADD COLUMN IF NOT EXISTS source_account_id INTEGER REFERENCES bank_accounts(id);
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS source_account_id INTEGER REFERENCES bank_accounts(id);
ALTER TABLE payroll_runs ADD COLUMN IF NOT EXISTS source_account_id INTEGER REFERENCES bank_accounts(id);

CREATE INDEX IF NOT EXISTS idx_acctx_account ON account_transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_acctx_date ON account_transactions(tx_date);
CREATE INDEX IF NOT EXISTS idx_bank_accounts_venue ON bank_accounts(venue_id);

COMMIT;
