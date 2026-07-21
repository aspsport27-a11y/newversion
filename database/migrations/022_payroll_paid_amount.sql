-- ============================================
-- Migration 022 — Payroll: nominal transfer aktual (manual)
-- Sebelumnya "Bayar (Transfer)" selalu memotong rekening sebesar total_net
-- (gaji bersih terhitung). Sekarang HO bisa entry nominal transfer manual
-- (mis. beda krn pembulatan/penyesuaian di luar sistem) — total_net tetap
-- sbg acuan perhitungan slip, paid_amount menyimpan nominal RIL yg keluar
-- dari rekening, dipakai juga saat "Batal Pengajuan" (revert) supaya yg
-- dibalikkan ke kas sesuai yg benar2 keluar, bukan asumsi total_net.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE payroll_runs ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(15,2);

COMMIT;
