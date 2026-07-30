-- 047: coaching padel — master coach, tarif coaching per venue, & penanda
-- coach/peserta di slot booking.
--
-- Konsep: coaching SELALU menempel pada booking court (tak berdiri sendiri).
-- Uangnya jadi order_item terpisah (item_type='coaching') supaya terpisah di
-- laporan, sedangkan coach & jumlah peserta disimpan di slot booking-nya —
-- itulah yg dipakai utk jadwal & proteksi coach dobel-booking.

CREATE TABLE IF NOT EXISTS coaches (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id),
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_coaches_venue ON coaches (venue_id);

-- tarif coaching per venue: harga utk 1 peserta + tambahan tiap peserta
-- berikutnya, per JAM. Belum sadar-hari (tarif seragam) — kolom bisa ditambah
-- nanti kalau perlu beda weekday/weekend.
CREATE TABLE IF NOT EXISTS coaching_rates (
    venue_id INTEGER PRIMARY KEY REFERENCES venues (id) ON DELETE CASCADE,
    base_price NUMERIC(15, 2) NOT NULL DEFAULT 0,
    extra_person_price NUMERIC(15, 2) NOT NULL DEFAULT 0,
    max_persons INTEGER NOT NULL DEFAULT 4,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE facility_bookings
    ADD COLUMN IF NOT EXISTS coach_id INTEGER REFERENCES coaches (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS coaching_persons INTEGER,
    -- link eksplisit ke baris uang coaching-nya, supaya reschedule/pembatalan
    -- bisa memperbarui/menemukan item yg tepat (1 order bisa punya banyak slot)
    ADD COLUMN IF NOT EXISTS coaching_item_id INTEGER REFERENCES order_items (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_fb_coach ON facility_bookings (coach_id, booking_date);

-- tarif awal Borneo Padel: Rp 250.000 (1 org) + Rp 50.000 per org tambahan
INSERT INTO coaching_rates (venue_id, base_price, extra_person_price, max_persons)
SELECT id, 250000, 50000, 4 FROM venues WHERE code = 'BP'
ON CONFLICT (venue_id) DO NOTHING;
