-- 049: coach mengisi ketersediaannya sendiri (pola mingguan + pengecualian).
--
-- Konsep: ini LAPISAN KETIGA, terpisah dari yg sudah ada —
--   court kosong?         -> facility_bookings (sudah ada)
--   coach belum mengajar? -> is_coach_available (sudah ada)
--   coach memang bisa?    -> tabel di bawah ini (baru)
--
-- Aturan baca: pengecualian tanggal SELALU menang atas pola mingguan.
-- Coach yg BELUM mengisi pola sama sekali dianggap "selalu bisa" — supaya
-- perilaku lama tak berubah & tak semua booking minta konfirmasi di hari-1.

CREATE TABLE IF NOT EXISTS coach_availability (
    id SERIAL PRIMARY KEY,
    coach_id INTEGER NOT NULL REFERENCES coaches (id) ON DELETE CASCADE,
    weekday SMALLINT NOT NULL,          -- 0=Senin .. 6=Minggu (ikut date.weekday() Python)
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_coach_avail_weekday CHECK (weekday BETWEEN 0 AND 6)
);
CREATE INDEX IF NOT EXISTS idx_coach_avail ON coach_availability (coach_id, weekday);

-- Pengecualian per tanggal:
--   available=FALSE (jam NULL)      -> libur seharian
--   available=TRUE  (jam terisi)    -> hanya jam itu, menimpa pola hari tsb
CREATE TABLE IF NOT EXISTS coach_availability_exceptions (
    id SERIAL PRIMARY KEY,
    coach_id INTEGER NOT NULL REFERENCES coaches (id) ON DELETE CASCADE,
    date DATE NOT NULL,
    available BOOLEAN NOT NULL DEFAULT FALSE,
    start_time TIME,
    end_time TIME,
    note VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_coach_avail_exc ON coach_availability_exceptions (coach_id, date);

-- kapan coach terakhir memperbarui ketersediaannya (utk manajer: ketahuan yg
-- tak pernah update)
ALTER TABLE coaches
    ADD COLUMN IF NOT EXISTS availability_updated_at TIMESTAMP;

-- jejak: booking ini dipaksakan di luar jam ketersediaan coach (kasir centang
-- konfirmasi "coach sudah setuju"). Dipakai kalau nanti ada sengketa.
ALTER TABLE facility_bookings
    ADD COLUMN IF NOT EXISTS coaching_override BOOLEAN NOT NULL DEFAULT FALSE;
