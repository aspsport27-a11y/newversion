-- ============================================
-- Migration 014 — RBAC configurable (Fase 2b)
-- Matriks role → izin (kapabilitas) yang bisa diatur dari UI.
-- Kehadiran baris = izin diberikan. Seed default = PERILAKU SEKARANG
-- (supaya tidak ada yang berubah sampai user menyentuh toggle).
-- Role 'admin' = superuser (bypass di kode, tak perlu baris).
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    role VARCHAR(20) NOT NULL,
    permission_code VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (role, permission_code)
);

-- ---- Seed default grants ----
INSERT INTO role_permissions (role, permission_code) VALUES
-- head_office: semua 17 izin
('head_office','report.business'),('head_office','report.management'),('head_office','holding.manage'),
('head_office','master.view'),('head_office','master.manage'),('head_office','hr.manage'),
('head_office','ops.view'),('head_office','ops.create'),('head_office','ops.approve'),
('head_office','proc.view'),('head_office','proc.create'),('head_office','proc.supplier'),('head_office','proc.pay'),
('head_office','payroll.view'),('head_office','payroll.generate'),('head_office','payroll.approve'),
('head_office','treasury.manage'),
-- manager_unit
('manager_unit','master.view'),('manager_unit','hr.manage'),
('manager_unit','ops.view'),('manager_unit','ops.create'),
('manager_unit','proc.view'),('manager_unit','proc.create'),
('manager_unit','payroll.view'),('manager_unit','payroll.generate'),
('manager_unit','report.business'),
-- admin_unit (koordinator area): hanya entry pengajuan dana
('admin_unit','ops.view'),('admin_unit','ops.create')
ON CONFLICT (role, permission_code) DO NOTHING;

COMMIT;
