-- Lokasi GPS saat absen masuk/pulang (verifikasi absen dari luar, tanpa masuk POS kasir)
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_in_location VARCHAR(100);
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_out_location VARCHAR(100);
