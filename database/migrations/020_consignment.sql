-- ============================================
-- Migration 020 — Konsinyasi (titip barang) + Settlement bagi hasil
-- Keputusan user: bagi hasil BUKAN persentase, tapi jumlah TETAP per unit
-- terjual (harga_bagi_hasil), disimpan PER PRODUK (bukan per supplier, krn
-- beda produk dr supplier yg sama biasa beda harga). Settlement MANUAL
-- (generate on-demand per venue+supplier+rentang tanggal), basis kas
-- (order status='paid', spt laporan penjualan yg sudah ada).
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE products ADD COLUMN IF NOT EXISTS is_consignment BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE products ADD COLUMN IF NOT EXISTS consignment_price NUMERIC(15,2);

CREATE TABLE IF NOT EXISTS consignment_settlements (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) UNIQUE NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    period_from DATE NOT NULL,
    period_to DATE NOT NULL,
    total_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_by INTEGER REFERENCES users(id),
    paid_at TIMESTAMP,
    source_account_id INTEGER REFERENCES bank_accounts(id)
);

CREATE TABLE IF NOT EXISTS consignment_settlement_items (
    id SERIAL PRIMARY KEY,
    settlement_id INTEGER NOT NULL REFERENCES consignment_settlements(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name VARCHAR(120) NOT NULL,
    quantity_sold NUMERIC(10,2) NOT NULL,
    unit_price NUMERIC(15,2) NOT NULL,  -- snapshot harga_bagi_hasil saat settlement dibuat
    subtotal NUMERIC(15,2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_consignment_settlements_venue_supplier
    ON consignment_settlements(venue_id, supplier_id);

COMMIT;
