-- ============================================
-- Migration 017 — Tiket (weekday/weekend) + Hari Libur
-- Tiket = produk bertanda is_ticket, kuota tak terbatas, punya 2 harga:
--   price (weekday) & weekend_price. Weekend = Sabtu/Minggu ATAU tanggal di `holidays`.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE products ADD COLUMN IF NOT EXISTS is_ticket BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE products ADD COLUMN IF NOT EXISTS weekend_price NUMERIC(15,2);

CREATE TABLE IF NOT EXISTS holidays (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tandai tiket yang sudah ada (waterpark) sebagai is_ticket
UPDATE products SET is_ticket = TRUE
WHERE sku ILIKE 'TKT%' OR name ILIKE '%tiket%';

COMMIT;
