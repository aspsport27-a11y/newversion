-- 069: izin baru 'transactions.view' (Lihat Riwayat Transaksi). Sebelumnya menu
-- Riwayat Transaksi dikunci daftar role tetap (admin/head_office/manager_unit).
-- Beri grant ke role yang selama ini sudah bisa (head_office & manager_unit)
-- supaya aksesnya tidak hilang. admin = superuser (tak perlu grant).
INSERT INTO role_permissions (role, permission_code)
SELECT r, 'transactions.view'
FROM (VALUES ('head_office'), ('manager_unit')) AS t(r)
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role = t.r AND rp.permission_code = 'transactions.view'
);
