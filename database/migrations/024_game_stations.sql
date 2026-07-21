-- ============================================
-- Migration 024 — Station Gaming (arena esport): data model Station + Session
-- Fase 1 dari konsep "POS venue esport" (sewa per-stasiun dgn timer berjalan).
-- Station = data master (spt Facility, tapi utk PS/PC/simulator, per venue,
-- ada tier krn tarif beda2 per tier). Session = 1 kali main (start s/d stop),
-- tarif per-jam DISALIN dari station saat start (rate_per_hour) spy perubahan
-- tarif nanti tak mengubah sesi yg sudah/sedang berjalan. Status station
-- (ready/ongoing) SENGAJA tidak disimpan sbg kolom — dihitung on-the-fly dari
-- ada/tidaknya sesi 'ongoing' pada station itu, biar tak ada risiko data
-- ganda yg bisa telat sinkron.
-- game_session_topups = riwayat "tambah jam/paket" manual selama sesi jalan
-- (durasi, diskon, total) — jadi baris tambahan saat sesi disettle jadi Order.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS game_stations (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    tier VARCHAR(20) NOT NULL DEFAULT 'reguler',  -- reguler|vip|simulator
    hourly_rate NUMERIC(15,2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(venue_id, code)
);

CREATE TABLE IF NOT EXISTS game_sessions (
    id SERIAL PRIMARY KEY,
    station_id INTEGER NOT NULL REFERENCES game_stations(id) ON DELETE CASCADE,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    customer_name VARCHAR(100),
    rate_per_hour NUMERIC(15,2) NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(12) NOT NULL DEFAULT 'ongoing',  -- ongoing|stopped
    stopped_at TIMESTAMP,
    order_id INTEGER REFERENCES orders(id),
    opened_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_game_sessions_station ON game_sessions(station_id);
CREATE INDEX IF NOT EXISTS idx_game_sessions_venue ON game_sessions(venue_id);
-- 1 station cuma boleh punya 1 sesi 'ongoing' aktif dalam satu waktu
CREATE UNIQUE INDEX IF NOT EXISTS uniq_station_ongoing_session
    ON game_sessions(station_id) WHERE status = 'ongoing';

CREATE TABLE IF NOT EXISTS game_session_topups (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    duration_minutes INTEGER NOT NULL,
    discount_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    total_amount NUMERIC(15,2) NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_game_session_topups_session ON game_session_topups(session_id);

COMMIT;
