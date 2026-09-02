-- 068: tanggal pengajuan dana (bisa dipilih di form Ajukan Dana). Backfill dari created_at.
ALTER TABLE op_requests ADD COLUMN IF NOT EXISTS req_date DATE;
UPDATE op_requests SET req_date = created_at::date WHERE req_date IS NULL;
