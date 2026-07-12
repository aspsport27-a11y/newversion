-- ============================================
-- Migration 008 — Operasional & Budget
-- Kategori pengeluaran custom, plafon budget per venue/bulan/kategori,
-- pengajuan dana (approval 1 level + pencairan) + rincian + lampiran bukti.
-- Tabel lama operational_requests & budget_allocation = DEPRECATED (dibiarkan).
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS expense_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(60) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Plafon budget per venue / bulan / kategori
CREATE TABLE IF NOT EXISTS budgets (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    category_id INTEGER NOT NULL REFERENCES expense_categories(id) ON DELETE CASCADE,
    amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (venue_id, year, month, category_id)
);

-- Pengajuan dana operasional (header)
CREATE TABLE IF NOT EXISTS op_requests (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) UNIQUE NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    created_by INTEGER REFERENCES users(id),
    total_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    description TEXT,
    status VARCHAR(12) NOT NULL DEFAULT 'submitted',  -- submitted|approved|rejected|disbursed
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    disbursed_by INTEGER REFERENCES users(id),
    disbursed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS op_request_items (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES op_requests(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES expense_categories(id),
    amount DECIMAL(15,2) NOT NULL,
    note VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS op_request_attachments (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES op_requests(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    stored_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    size_bytes INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_budgets_lookup ON budgets(venue_id, year, month);
CREATE INDEX IF NOT EXISTS idx_op_requests_venue ON op_requests(venue_id);
CREATE INDEX IF NOT EXISTS idx_op_requests_status ON op_requests(status);
CREATE INDEX IF NOT EXISTS idx_op_items_request ON op_request_items(request_id);

-- Seed 9 kategori
INSERT INTO expense_categories (name, sort_order) VALUES
    ('Ops Kas Unit', 1), ('Ops Marketing', 2), ('Ops Maintenance', 3),
    ('Ops Event', 4), ('Ops Fisio', 5), ('Utilitas', 6),
    ('BPJS TK', 7), ('BPJS KS', 8), ('Sumbangan', 9)
ON CONFLICT (name) DO NOTHING;

COMMIT;
