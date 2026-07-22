-- Kategori beban Operasional bisa di-scope ke venue tertentu (bukan cuma global).
-- NULL = global (dipakai semua venue); terisi = cuma muncul di venue tsb.
ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS venue_id INTEGER REFERENCES venues(id) ON DELETE CASCADE;
