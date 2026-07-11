-- ============================================
-- Migration 002 — POS M0
-- Mesin transaksi generik: orders/order_items/payments,
-- products (per-venue, stok F&B), shifts+rekonsiliasi kas, facilities/booking.
-- Target DB: venue_system. Idempotent (aman dijalankan ulang).
-- ============================================
BEGIN;

-- ============================================
-- A. MASTER & TERMINAL
-- ============================================
CREATE TABLE IF NOT EXISTS pos_terminals (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'other',  -- food|drink|ticket|rental|other
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(30) UNIQUE NOT NULL,
    name VARCHAR(120) NOT NULL,
    category_id INTEGER REFERENCES product_categories(id) ON DELETE SET NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,  -- per-venue
    price DECIMAL(15,2) NOT NULL DEFAULT 0,
    unit VARCHAR(20) DEFAULT 'pcs',
    track_stock BOOLEAN DEFAULT TRUE,       -- F&B: pelacakan stok aktif
    stock_qty INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facilities (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50),
    hourly_rate DECIMAL(15,2) NOT NULL DEFAULT 0,
    open_time TIME DEFAULT '08:00',
    close_time TIME DEFAULT '23:00',
    slot_minutes INTEGER DEFAULT 60,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- C. SHIFT & REKONSILIASI KAS
-- ============================================
CREATE TABLE IF NOT EXISTS shifts (
    id SERIAL PRIMARY KEY,
    terminal_id INTEGER NOT NULL REFERENCES pos_terminals(id),
    venue_id INTEGER NOT NULL REFERENCES venues(id),
    cashier_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(10) NOT NULL DEFAULT 'open',   -- open|closed
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    opening_cash DECIMAL(15,2) NOT NULL DEFAULT 0,   -- saldo awal laci
    total_cash_sales DECIMAL(15,2) DEFAULT 0,
    total_qris_sales DECIMAL(15,2) DEFAULT 0,
    total_sales DECIMAL(15,2) DEFAULT 0,
    cash_in DECIMAL(15,2) DEFAULT 0,
    cash_out DECIMAL(15,2) DEFAULT 0,
    expected_cash DECIMAL(15,2) DEFAULT 0,   -- opening + cash_sales + cash_in - cash_out
    counted_cash DECIMAL(15,2),              -- hasil hitung fisik
    cash_variance DECIMAL(15,2),             -- counted - expected
    deposit_amount DECIMAL(15,2),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS cash_movements (
    id SERIAL PRIMARY KEY,
    shift_id INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    type VARCHAR(4) NOT NULL,                -- in|out
    amount DECIMAL(15,2) NOT NULL,
    reason VARCHAR(200),
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- B. ORDERS (mesin transaksi)
-- ============================================
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_number VARCHAR(30) UNIQUE NOT NULL,   -- mis. V001-20260711-0007
    venue_id INTEGER NOT NULL REFERENCES venues(id),
    terminal_id INTEGER REFERENCES pos_terminals(id),
    shift_id INTEGER REFERENCES shifts(id),
    cashier_id INTEGER REFERENCES users(id),
    customer_name VARCHAR(100),
    customer_phone VARCHAR(20),
    status VARCHAR(10) NOT NULL DEFAULT 'open', -- open|paid|void
    subtotal DECIMAL(15,2) NOT NULL DEFAULT 0,
    discount_amount DECIMAL(15,2) NOT NULL DEFAULT 0,  -- diskon level order
    total_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_type VARCHAR(10) NOT NULL,          -- product|ticket|rental|booking
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    name_snapshot VARCHAR(120) NOT NULL,     -- nama saat jual (histori)
    unit_price DECIMAL(15,2) NOT NULL,       -- harga saat jual (histori)
    quantity DECIMAL(10,2) NOT NULL DEFAULT 1,  -- produk: jumlah; booking: jam
    line_total DECIMAL(15,2) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    method VARCHAR(10) NOT NULL,             -- cash|qris
    provider VARCHAR(30) NOT NULL DEFAULT 'cash',  -- cash|qris_bank_manual|midtrans...
    amount DECIMAL(15,2) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'pending', -- pending|paid|failed
    reference VARCHAR(100),                  -- ref bank / 4 digit
    confirmed_by INTEGER REFERENCES users(id),
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- D. BOOKING (tabel disiapkan; UI di M2)
-- ============================================
CREATE TABLE IF NOT EXISTS facility_bookings (
    id SERIAL PRIMARY KEY,
    facility_id INTEGER NOT NULL REFERENCES facilities(id),
    venue_id INTEGER NOT NULL REFERENCES venues(id),
    order_item_id INTEGER REFERENCES order_items(id) ON DELETE SET NULL,
    booking_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'booked',  -- booked|cancelled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- E. STOCK MOVEMENTS (audit stok F&B)
-- ============================================
CREATE TABLE IF NOT EXISTS stock_movements (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    venue_id INTEGER NOT NULL REFERENCES venues(id),
    type VARCHAR(12) NOT NULL,               -- sale|purchase|adjustment|return
    quantity INTEGER NOT NULL,               -- bertanda: negatif = keluar
    balance_after INTEGER,
    reference VARCHAR(50),                   -- mis. order_number
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- USERS: PIN login POS + binding venue (opsional)
-- ============================================
ALTER TABLE users ADD COLUMN IF NOT EXISTS pin_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS venue_id INTEGER REFERENCES venues(id);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX IF NOT EXISTS idx_products_venue ON products(venue_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_facilities_venue ON facilities(venue_id);
CREATE INDEX IF NOT EXISTS idx_shifts_terminal ON shifts(terminal_id);
CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts(status);
CREATE INDEX IF NOT EXISTS idx_orders_venue ON orders(venue_id);
CREATE INDEX IF NOT EXISTS idx_orders_shift ON orders(shift_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_fbookings_facility_date ON facility_bookings(facility_id, booking_date);
CREATE INDEX IF NOT EXISTS idx_stock_mov_product ON stock_movements(product_id);

COMMIT;
