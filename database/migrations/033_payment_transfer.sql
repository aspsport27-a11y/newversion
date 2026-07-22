-- ============================================
-- Migration 033 — Metode bayar Transfer Bank + bukti transfer
-- Tambah kolom proof_image di payments (filename bukti transfer/screenshot)
-- dan total_transfer_sales di shifts (rekap per shift, terpisah dari cash/qris
-- krn uangnya tak masuk laci fisik & tak lewat provider QRIS).
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE payments ADD COLUMN IF NOT EXISTS proof_image VARCHAR(255);
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS total_transfer_sales NUMERIC(15, 2) DEFAULT 0;

COMMIT;
