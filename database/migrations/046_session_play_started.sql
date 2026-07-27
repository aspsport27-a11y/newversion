-- 046: pisahkan "sudah dibayar" dari "sudah main". play_started_at diisi saat
-- kasir klik PLAY (mulai main) — timer station & add-on baru berjalan dari sini.
-- NULL = sudah dibayar tapi belum dimainkan. Sesi lama (NULL + started_at lama)
-- diperlakukan sudah main sejak started_at (backward-compat, lihat frontend).

ALTER TABLE game_sessions
    ADD COLUMN IF NOT EXISTS play_started_at TIMESTAMP;
