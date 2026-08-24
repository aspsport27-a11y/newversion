-- 057: rincian LPJ per baris (banyak item). Tiap baris = 1 pengeluaran nyata
-- (tanggal, keterangan, kategori, jumlah). Dijumlahkan per kategori otomatis →
-- mengisi op_request_items.realized_amount (rollup). Kategori dibatasi ke kategori
-- yg ada di pengajuan. Nota pakai lampiran 'Bukti' gabungan yg sudah ada.
CREATE TABLE IF NOT EXISTS op_realization_lines (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES op_requests(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES expense_categories(id),
    line_date DATE,
    description VARCHAR(200),
    amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_op_realization_req ON op_realization_lines (request_id);
