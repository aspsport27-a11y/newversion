-- 059: kategori beban boleh nama sama untuk venue berbeda (global + per-venue).
-- Sebelumnya UNIQUE(name) global — bikin 500 saat tambah kategori venue yg namanya
-- sama dgn kategori global/venue lain. Ganti jadi unik per (name, venue) dgn
-- COALESCE(venue_id,0) supaya 2 kategori global bernama sama tetap ditolak, tapi
-- global "X" & venue "X" boleh berdampingan. (Cek app sudah pakai (name, venue_id).)
ALTER TABLE expense_categories DROP CONSTRAINT IF EXISTS expense_categories_name_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_expense_cat_name_venue
    ON expense_categories (name, COALESCE(venue_id, 0));
