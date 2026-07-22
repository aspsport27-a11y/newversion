-- ============================================
-- Migration 032 — Tarif per rentang jam per facility (facility_rate_rules)
-- 1 lapangan bisa punya harga beda-beda tergantung jam (mis. malam lebih
-- mahal dari siang). Kalau jam booking tak match rule manapun, dipakai
-- Facility.hourly_rate (tarif dasar) sbg fallback.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS facility_rate_rules (
    id SERIAL PRIMARY KEY,
    facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    label VARCHAR(50),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    hourly_rate NUMERIC(15, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_facility_rate_rules_facility ON facility_rate_rules(facility_id);

COMMIT;
