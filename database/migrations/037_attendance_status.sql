-- ============================================
-- Migration 037 — attendance.status (izin/sakit/cuti)
-- Keterangan tak-hadir karyawan: izin | sakit | cuti. NULL = hari kerja normal
-- (status hadir/belum absen/alpha dihitung dari check_in). Ditandai manual di
-- portal oleh manajer/admin/HO. Dipakai roster kehadiran + laporan izin/sakit/cuti.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE attendance ADD COLUMN IF NOT EXISTS status VARCHAR(10);

COMMIT;
