-- 056: Realisasi / LPJ pengeluaran operasional. Setelah dana DICAIRKAN ke venue,
-- venue lapor pemakaian AKTUAL per kategori. Sisa (diajukan - terpakai) otomatis
-- dikembalikan ke kas (rekening sumber pencairan). Tanpa approval HO (venue lapor
-- langsung). realized_at != NULL = sudah dipertanggungjawabkan (LPJ).
ALTER TABLE op_request_items ADD COLUMN IF NOT EXISTS realized_amount NUMERIC(15,2);

ALTER TABLE op_requests ADD COLUMN IF NOT EXISTS realized_at TIMESTAMP;
ALTER TABLE op_requests ADD COLUMN IF NOT EXISTS realized_by INTEGER REFERENCES users(id);
ALTER TABLE op_requests ADD COLUMN IF NOT EXISTS realized_total NUMERIC(15,2);
ALTER TABLE op_requests ADD COLUMN IF NOT EXISTS returned_amount NUMERIC(15,2);
ALTER TABLE op_requests ADD COLUMN IF NOT EXISTS returned_account_id INTEGER REFERENCES bank_accounts(id);
