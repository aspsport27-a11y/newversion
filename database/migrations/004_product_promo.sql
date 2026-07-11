-- ============================================
-- Migration 004 — harga promo produk/tiket
-- promo_price: bila diisi (>0 dan < price) menjadi harga jual efektif.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;
ALTER TABLE products ADD COLUMN IF NOT EXISTS promo_price DECIMAL(15,2);
COMMIT;
