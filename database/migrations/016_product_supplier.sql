-- ============================================
-- Migration 016 — Supplier default per produk
-- Tiap produk boleh punya supplier default → memudahkan buat PO (auto isi supplier).
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL;

COMMIT;
