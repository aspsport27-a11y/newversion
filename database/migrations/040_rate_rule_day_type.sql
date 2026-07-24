-- 040: tarif lapangan (facility_rate_rules) jadi sadar-hari.
-- Sebelumnya tarif hanya punya rentang jam; tarif Weekday/Sabtu/Minggu saling
-- bertabrakan pada jam yg sama & "yg cocok pertama menang" bikin harga tak
-- deterministik (preview beda dgn tagihan). Kolom day_type memisahkannya.

ALTER TABLE facility_rate_rules
    ADD COLUMN IF NOT EXISTS day_type VARCHAR(10) NOT NULL DEFAULT 'weekday';

-- Backfill dari label yg sudah ada (Weekday/Sabtu/Minggu/Libur).
UPDATE facility_rate_rules SET day_type = 'sunday'
    WHERE lower(coalesce(label, '')) LIKE '%minggu%';
UPDATE facility_rate_rules SET day_type = 'saturday'
    WHERE lower(coalesce(label, '')) LIKE '%sabtu%';
UPDATE facility_rate_rules SET day_type = 'holiday'
    WHERE lower(coalesce(label, '')) LIKE '%libur%'
       OR lower(coalesce(label, '')) LIKE '%holiday%';
-- sisanya tetap 'weekday' (default).

CREATE INDEX IF NOT EXISTS idx_rate_rules_facility_day
    ON facility_rate_rules (facility_id, day_type);
