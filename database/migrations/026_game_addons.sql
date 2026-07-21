-- ============================================
-- Migration 026 — Add-on perangkat tambahan (stick ekstra, VR, setir racing dll)
-- Ditagih PER JAM mengikuti durasi sesi utama (bukan flat) — jadi game_addons
-- itu katalog (nama + tarif/jam per venue), game_session_addons itu yg
-- nempel ke satu sesi tertentu (bisa lebih dari 1 add-on, bisa qty >1).
-- rate_per_hour DISALIN saat addon ditempelkan ke sesi (sama pola dgn
-- session.rate_per_hour) spy perubahan tarif nanti tak mengubah sesi berjalan.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS game_addons (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    hourly_rate NUMERIC(15,2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS game_session_addons (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    addon_id INTEGER NOT NULL REFERENCES game_addons(id),
    name_snapshot VARCHAR(100) NOT NULL,
    rate_per_hour NUMERIC(15,2) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_game_session_addons_session ON game_session_addons(session_id);

COMMIT;
