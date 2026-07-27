-- 043: penanda order booking member (utk CRM Data Customer & laporan).
-- Diisi TRUE saat booking member dibuat. Backfill data lama pakai heuristik:
-- order dgn >1 slot booking = pola member (berulang di banyak tanggal).

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS is_member BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE orders o SET is_member = TRUE
WHERE (
    SELECT COUNT(*) FROM order_items i
    WHERE i.order_id = o.id AND i.item_type = 'booking'
) > 1;
