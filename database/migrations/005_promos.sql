-- ============================================
-- Migration 005 — sistem promo fleksibel
-- Tipe: price (harga promo) | percent (diskon %) | bogo (beli X gratis Y)
-- Periode tanggal opsional (start_date/end_date). Per produk.
-- Menggantikan products.promo_price (kolom lama dibiarkan, tak dipakai).
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS promos (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    type VARCHAR(10) NOT NULL DEFAULT 'price',   -- price|percent|bogo
    promo_price DECIMAL(15,2),                    -- type=price
    percent DECIMAL(5,2),                         -- type=percent (mis. 20 = 20%)
    buy_qty INTEGER,                              -- type=bogo
    get_qty INTEGER,                              -- type=bogo
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_promos_product ON promos(product_id);
CREATE INDEX IF NOT EXISTS idx_promos_active ON promos(is_active);

COMMIT;
