-- 051: entri lembur manual per karyawan per periode.
--
-- Sengaja TERPISAH dari payroll_items (tab sendiri di menu Payroll): manajer/admin
-- input nilai lembur (Rupiah) manual per bulan. Untuk sekarang BARU pencatatan —
-- BELUM diikat ke perhitungan net gaji di payroll_runs (bisa disambung nanti tanpa
-- ubah struktur). Unik per (karyawan, tahun, bulan) supaya 1 entri per periode.
CREATE TABLE IF NOT EXISTS overtime_entries (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    venue_id INTEGER REFERENCES venues(id) ON DELETE SET NULL,
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL,
    amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    note VARCHAR(200),
    updated_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (employee_id, period_year, period_month)
);

CREATE INDEX IF NOT EXISTS idx_overtime_venue_period
    ON overtime_entries (venue_id, period_year, period_month);
