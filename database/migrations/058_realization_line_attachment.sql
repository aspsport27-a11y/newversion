-- 058: lampiran nota per baris rincian LPJ (user minta upload bukti tiap baris).
-- File disimpan di folder upload yg sama (oprequests); baris menyimpan referensinya.
ALTER TABLE op_realization_lines ADD COLUMN IF NOT EXISTS attachment_stored VARCHAR(255);
ALTER TABLE op_realization_lines ADD COLUMN IF NOT EXISTS attachment_name VARCHAR(255);
ALTER TABLE op_realization_lines ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(100);
