-- ============================================
-- Migration 015 — Absensi (kehadiran) staff via terminal POS
-- Staff tap PIN di terminal → Absen Masuk / Pulang. Rekap kehadiran saja
-- (belum terhubung payroll). 1 baris per user per hari.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    venue_id INTEGER REFERENCES venues(id) ON DELETE CASCADE,
    terminal_id INTEGER REFERENCES pos_terminals(id) ON DELETE SET NULL,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    check_in TIMESTAMP,
    check_out TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_attendance_venue_date ON attendance(venue_id, date);

COMMIT;
