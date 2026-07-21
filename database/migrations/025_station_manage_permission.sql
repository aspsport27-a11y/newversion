-- ============================================
-- Migration 025 — Izin baru "station.manage" (Kelola Station Gaming)
-- Bagian dari Fase 1 modul Station Gaming (POS venue esport). Manager_unit &
-- head_office dapat izin ini secara default, spy bisa kelola data master
-- station (nama, tier, tarif/jam) venue mereka sendiri lewat portal admin.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

INSERT INTO role_permissions (role, permission_code)
SELECT 'manager_unit', 'station.manage'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions WHERE role='manager_unit' AND permission_code='station.manage'
);

INSERT INTO role_permissions (role, permission_code)
SELECT 'head_office', 'station.manage'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions WHERE role='head_office' AND permission_code='station.manage'
);

COMMIT;
