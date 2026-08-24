-- 055: token rahasia per venue untuk "Papan Jadwal Layar" (TV di venue).
-- Halaman layar.html (jadwal.aspsports.id) buka pakai ?token=<display_token>,
-- menampilkan jadwal booking per lapangan hari ini + NAMA DEPAN customer — tanpa
-- login. Beda dari jadwal publik biasa (yg anonim): ini token-gated & internal.
ALTER TABLE venues ADD COLUMN IF NOT EXISTS display_token VARCHAR(64) UNIQUE;
