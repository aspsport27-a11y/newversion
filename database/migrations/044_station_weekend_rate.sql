-- 044: tarif akhir pekan untuk station gaming (W Arena) — 2 harga per station.
-- weekend_rate NULL = pakai hourly_rate (weekday) juga di akhir pekan.

ALTER TABLE game_stations
    ADD COLUMN IF NOT EXISTS weekend_rate NUMERIC(15, 2);
