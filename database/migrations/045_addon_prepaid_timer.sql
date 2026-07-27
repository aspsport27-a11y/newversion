-- 045: add-on sesi jadi PRABAYAR + timer sendiri (Tahap C W Arena).
-- booked_minutes = durasi sewa add-on (terpisah dari station), started_at = mulai
-- timer add-on, total_amount = biaya prabayar. Add-on lama (booked_minutes 0) =
-- ikut durasi sesi & ditagih di stop (perilaku lama, backward-compat).

ALTER TABLE game_session_addons
    ADD COLUMN IF NOT EXISTS booked_minutes INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS total_amount NUMERIC(15, 2);
