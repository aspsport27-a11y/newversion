-- Alamat hasil reverse geocoding (Nominatim/OSM) dari koordinat absen, disimpan
-- sekali saat absen supaya tidak perlu panggil API tiap kali daftar dibuka.
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_in_address VARCHAR(255);
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_out_address VARCHAR(255);
