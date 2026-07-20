-- ============================================
-- Migration 019 — Pecah izin 'master.manage' jadi granular per-resource
-- Supaya admin_unit bisa dikasih akses HANYA produk/lapangan/promo,
-- tanpa venue/area/setup (permintaan user).
-- Kode baru: venue.manage, area.manage, product.manage, promo.manage,
--            facility.manage, setup.manage, order.cancel
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

-- head_office: pertahankan cakupan penuh spt master.manage sebelumnya
INSERT INTO role_permissions (role, permission_code)
SELECT 'head_office', code FROM (VALUES
    ('venue.manage'), ('area.manage'), ('product.manage'), ('promo.manage'),
    ('facility.manage'), ('setup.manage'), ('order.cancel')
) AS t(code)
WHERE EXISTS (SELECT 1 FROM role_permissions WHERE role='head_office' AND permission_code='master.manage')
ON CONFLICT (role, permission_code) DO NOTHING;

-- admin_unit: HANYA produk, lapangan (facility, termasuk tiket & hari libur), promo
-- + master.view (baca) krn endpoint list produk/lapangan/promo butuh izin ini
-- supaya halamannya bisa memuat data, bukan cuma bisa kelola.
INSERT INTO role_permissions (role, permission_code)
SELECT 'admin_unit', code FROM (VALUES
    ('product.manage'), ('facility.manage'), ('promo.manage'), ('master.view')
) AS t(code)
WHERE EXISTS (SELECT 1 FROM role_permissions WHERE role='admin_unit' AND permission_code='master.manage')
ON CONFLICT (role, permission_code) DO NOTHING;

-- hapus kode lama yg sudah tak dipakai kode manapun
DELETE FROM role_permissions WHERE permission_code = 'master.manage';

COMMIT;
