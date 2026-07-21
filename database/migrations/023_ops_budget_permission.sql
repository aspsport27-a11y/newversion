-- ============================================
-- Migration 023 — Izin baru "ops.budget" (Kelola plafon budget)
-- Sebelumnya plafon budget cuma bisa diedit oleh siapa yg punya ops.approve
-- (Setujui & cairkan dana) — jadi manager_unit (yg cuma pegang ops.view/create)
-- tak bisa atur plafon venue-nya sendiri walau itu wajar buat mereka.
-- Dipecah jadi izin tersendiri spy tak otomatis kebawa kasih hak approve
-- pengajuan dana (yg tetap harus lewat HO).
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

INSERT INTO role_permissions (role, permission_code)
SELECT 'manager_unit', 'ops.budget'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions WHERE role='manager_unit' AND permission_code='ops.budget'
);

INSERT INTO role_permissions (role, permission_code)
SELECT 'head_office', 'ops.budget'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions WHERE role='head_office' AND permission_code='ops.budget'
);

COMMIT;
