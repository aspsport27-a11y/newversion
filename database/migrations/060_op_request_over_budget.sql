-- 060: tandai pengajuan dana yg MELEBIHI sisa budget kategori. Tetap boleh diajukan
-- (tak diblok), tapi ditandai supaya HO tahu perlu perhatian khusus.
ALTER TABLE op_requests ADD COLUMN IF NOT EXISTS over_budget BOOLEAN NOT NULL DEFAULT false;
