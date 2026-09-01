-- 067: tanggal PO (bisa dipilih di form Buat PO). Backfill dari created_at.
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS order_date DATE;
UPDATE purchase_orders SET order_date = created_at::date WHERE order_date IS NULL;
