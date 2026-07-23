-- ============================================
-- Migration 035 — game_sessions.booked_minutes (paket waktu awal)
-- Ubah model sewa Station Gaming: dari per-menit terpakai (meteran elapsed)
-- jadi PAKET TETAP — kasir entry "mau main berapa jam" saat mulai sesi,
-- harga sewa station langsung fix = jam dipesan x tarif/jam (bukan dihitung
-- per menit yg berjalan). Jam di layar = hitung mundur dari paket ini.
-- Sesi lama (booked_minutes=0) tetap pakai perhitungan elapsed lama (fallback
-- di kode) supaya tak berubah retroaktif.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE game_sessions ADD COLUMN IF NOT EXISTS booked_minutes INTEGER NOT NULL DEFAULT 0;

COMMIT;
