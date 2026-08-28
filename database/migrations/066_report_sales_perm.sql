-- 066: izin baru 'report.sales' (Lihat Laporan Penjualan). Sebelumnya Laporan
-- Penjualan memakai 'master.view'. Beri grant ke role yang selama ini sudah bisa
-- (head_office & manager_unit) supaya aksesnya tidak hilang. admin = superuser.
INSERT INTO role_permissions (role, permission_code)
SELECT r, 'report.sales'
FROM (VALUES ('head_office'), ('manager_unit')) AS t(r)
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role = t.r AND rp.permission_code = 'report.sales'
);
