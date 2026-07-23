-- ============================================
-- Migration 038 — purchase_orders.kind ('sale' | 'ops')
-- 'sale'  = Procurement biasa (barang utk dijual, item stok bisa nambah stok)
-- 'ops'   = Procurement Ops (keperluan rumah tangga venue — semua item non-stok,
--           TIDAK pernah jadi stok jual, cuma record + alur beli/approve/terima/bayar)
-- Mesin/tabel sama, dibedakan menu & filter kind. Baris lama = 'sale'.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS kind VARCHAR(10) NOT NULL DEFAULT 'sale';

COMMIT;
