-- ============================================
-- Migration 018 — Foto wajah bukti absen (anti-manipulasi)
-- Saat absen di terminal, kamera jepret foto → disimpan sbg bukti.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_in_photo VARCHAR(255);
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_out_photo VARCHAR(255);

COMMIT;
