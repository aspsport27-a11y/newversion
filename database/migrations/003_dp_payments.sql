-- ============================================
-- Migration 003 — DP / pembayaran sebagian + pelunasan
-- - orders.amount_paid: akumulasi yang sudah dibayar (sisa = total - amount_paid)
-- - payments.shift_id: shift yang MENERIMA pembayaran (untuk rekonsiliasi per-kas)
--   sehingga DP & pelunasan terhitung di shift masing-masing.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE orders ADD COLUMN IF NOT EXISTS amount_paid DECIMAL(15,2) DEFAULT 0;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS shift_id INTEGER REFERENCES shifts(id);

-- status order sekarang: open | partial | paid | void

CREATE INDEX IF NOT EXISTS idx_payments_shift ON payments(shift_id);
CREATE INDEX IF NOT EXISTS idx_payments_paid_at ON payments(paid_at);

COMMIT;
