-- 048: tautan jadwal pribadi coach.
--
-- Halaman jadwal coach dibuka TANPA login & memuat nama + no HP customer,
-- jadi kuncinya token RAHASIA yg tak bisa ditebak (bukan ?coach_id=7 yg
-- gampang di-enumerasi). Token di-generate di Python pakai secrets, bukan
-- random() SQL. Kalau bocor, token bisa di-reset dr portal (token lama mati).

ALTER TABLE coaches
    ADD COLUMN IF NOT EXISTS schedule_token VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coaches_token
    ON coaches (schedule_token) WHERE schedule_token IS NOT NULL;
