-- 052: header status/approval untuk lembur — konsep sama dgn payroll_runs.
--
-- overtime_entries (migrasi 051) = item per karyawan. Tabel ini = "batch" per
-- venue+periode yg menyimpan STATUS alur pengajuan: draft → submitted (diajukan
-- ke HO) → approved / rejected. Manajer isi & ajukan; HO setujui/tolak. Entri
-- terkait via (venue_id, period_year, period_month), bukan FK, supaya entri yg
-- sudah ada tak perlu dimigrasi. Belum ada tahap 'paid' (lembur belum diikat ke
-- pencairan uang) — bisa ditambah nanti tanpa ubah struktur.
CREATE TABLE IF NOT EXISTS overtime_runs (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'draft',  -- draft|submitted|approved|rejected
    total_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id),
    submitted_at TIMESTAMP,
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (venue_id, period_year, period_month)
);
