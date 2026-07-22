-- ============================================
-- Migration 031 — Izin baru "ops.category" (Kelola kategori beban, venue sendiri)
-- Sebelumnya kelola kategori cuma bisa oleh siapa yg punya ops.approve
-- (admin/head_office) — manager_unit tidak bisa entry kategori beban venuenya
-- sendiri, padahal mereka yg paling tau pengeluaran venue. Dipecah jadi izin
-- tersendiri (dibatasi ke venue sendiri di level aplikasi) spy tak otomatis
-- kebawa hak approve pengajuan dana (yg tetap harus lewat HO).
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

INSERT INTO role_permissions (role, permission_code)
SELECT 'manager_unit', 'ops.category'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions WHERE role='manager_unit' AND permission_code='ops.category'
);

COMMIT;
