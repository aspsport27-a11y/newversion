-- 071: event bisa memilih SEBAGIAN lapangan (tak selalu borong semua). Tabel
-- pivot event↔lapangan. Event LAMA tanpa baris di sini = tetap "semua lapangan"
-- (backward compatible). Event BARU menyimpan daftar lapangan terpilih.
CREATE TABLE IF NOT EXISTS event_facilities (
    event_id    INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    facility_id INT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, facility_id)
);
CREATE INDEX IF NOT EXISTS idx_event_facilities_facility ON event_facilities(facility_id);
