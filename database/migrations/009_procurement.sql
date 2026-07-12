-- ============================================
-- Migration 009 — Procurement (PO) + stok masuk + reorder alert
-- Alur: submitted -> approved (HO) -> received (stok masuk) -> paid (HO bayar).
-- Item PO yang punya product_id -> saat diterima nambah products.stock_qty.
-- products.min_stock = ambang reorder (stok menipis).
-- Reuse tabel suppliers (schema awal). op_request_attachments pola sama.
-- Tabel lama procurement_requests/procurement_items/inventory/stock_transactions = DEPRECATED.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE products ADD COLUMN IF NOT EXISTS min_stock INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS purchase_orders (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) UNIQUE NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    supplier_id INTEGER REFERENCES suppliers(id),
    created_by INTEGER REFERENCES users(id),
    total_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    notes TEXT,
    status VARCHAR(12) NOT NULL DEFAULT 'submitted',  -- submitted|approved|received|paid|rejected
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    received_by INTEGER REFERENCES users(id),
    received_at TIMESTAMP,
    paid_by INTEGER REFERENCES users(id),
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    id SERIAL PRIMARY KEY,
    po_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,  -- NULL = non-stok
    item_name VARCHAR(120) NOT NULL,
    quantity INTEGER NOT NULL,
    unit VARCHAR(20),
    unit_price DECIMAL(15,2) NOT NULL,
    total_price DECIMAL(15,2) NOT NULL,
    note VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS po_attachments (
    id SERIAL PRIMARY KEY,
    po_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    stored_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    size_bytes INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_po_venue ON purchase_orders(venue_id);
CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);
CREATE INDEX IF NOT EXISTS idx_po_items_po ON purchase_order_items(po_id);

COMMIT;
