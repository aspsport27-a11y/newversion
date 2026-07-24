-- 041: produk harga terbuka (open_price) — nominal diketik kasir saat transaksi
-- (mis. Parkir), bukan harga tetap katalog. Tanpa stok, tanpa promo.

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS open_price BOOLEAN NOT NULL DEFAULT FALSE;
