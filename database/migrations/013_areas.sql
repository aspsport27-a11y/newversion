-- ============================================
-- Migration 013 — Struktur Area + role Admin Unit (Fase 2a)
-- Area = kumpulan beberapa venue. Admin Unit = role junior (di bawah manajer),
-- scope AREA, hanya boleh input pengajuan dana (op_request) utk venue di areanya
-- → langsung ke HO utk approve/cairkan.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS areas (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- venue masuk ke satu area (opsional)
ALTER TABLE venues ADD COLUMN IF NOT EXISTS area_id INTEGER REFERENCES areas(id) ON DELETE SET NULL;

-- user Admin Unit di-assign ke satu area (scope-nya)
ALTER TABLE users ADD COLUMN IF NOT EXISTS area_id INTEGER REFERENCES areas(id) ON DELETE SET NULL;

COMMIT;
