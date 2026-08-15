-- 053: generalkan "lembur" jadi entri manual berkategori — supaya 1 mesin bisa
-- melayani beberapa kategori pengajuan (lembur, reward, pekerjaan tambahan) tanpa
-- menduplikasi tabel/endpoint. Baris lama otomatis kategori 'lembur'.
ALTER TABLE overtime_runs ADD COLUMN IF NOT EXISTS category VARCHAR(20) NOT NULL DEFAULT 'lembur';
ALTER TABLE overtime_entries ADD COLUMN IF NOT EXISTS category VARCHAR(20) NOT NULL DEFAULT 'lembur';

-- unique lama tak lagi cukup (harus per kategori juga) — ganti.
ALTER TABLE overtime_runs DROP CONSTRAINT IF EXISTS overtime_runs_venue_id_period_year_period_month_key;
ALTER TABLE overtime_entries DROP CONSTRAINT IF EXISTS overtime_entries_employee_id_period_year_period_month_key;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_overtime_run_cat') THEN
    ALTER TABLE overtime_runs ADD CONSTRAINT uq_overtime_run_cat
      UNIQUE (venue_id, period_year, period_month, category);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_overtime_entry_cat') THEN
    ALTER TABLE overtime_entries ADD CONSTRAINT uq_overtime_entry_cat
      UNIQUE (employee_id, period_year, period_month, category);
  END IF;
END $$;
