-- 050: reservasi station (W Arena) — pesan di muka per JENIS station.
--
-- Beda mendasar dgn booking lapangan: sesi station TAK punya akhir pasti
-- (customer bisa "tambah waktu" — 36% sesi begitu). Karena itu yg dipesan
-- adalah JENIS station, bukan unit tertentu: bentrok baru terjadi kalau SEMUA
-- unit jenis itu terpakai, jadi sesi yg molor di satu unit bisa diserap unit
-- lain. Unit ditentukan saat customer datang (seperti reservasi meja restoran).
--
-- Uang: reservasi bikin Order berisi biaya durasi (prabayar, pola sama dgn
-- station_start). Saat customer datang, GameSession dibuat menaut order yg
-- SAMA (session.order_id) — station_stop sudah tahu sesi ber-order = prabayar
-- & cuma menambah F&B/add-on, jadi tak ada dobel tagih.

ALTER TABLE game_stations
    ADD COLUMN IF NOT EXISTS station_type VARCHAR(50);

-- kelompokkan station yg ada dari namanya (bisa diubah lewat portal nanti)
UPDATE game_stations SET station_type = CASE
    WHEN name ILIKE 'ruangan vip%'  THEN 'Ruangan VIP'
    WHEN name ILIKE 'simulator ps%' THEN 'Simulator PS'
    WHEN name ILIKE 'simulator pc%' THEN 'Simulator PC'
    ELSE 'Reguler'
END
WHERE station_type IS NULL;

CREATE TABLE IF NOT EXISTS station_reservations (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues (id) ON DELETE CASCADE,
    station_type VARCHAR(50) NOT NULL,
    reservation_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    duration_minutes INTEGER NOT NULL,
    customer_name VARCHAR(100),
    customer_phone VARCHAR(20),
    -- order berisi biaya durasi; DP/pelunasan lewat jalur pembayaran biasa
    order_id INTEGER REFERENCES orders (id) ON DELETE SET NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'booked',   -- booked|fulfilled|cancelled
    -- diisi saat customer datang & kasir menentukan unitnya
    station_id INTEGER REFERENCES game_stations (id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES game_sessions (id) ON DELETE SET NULL,
    created_by INTEGER REFERENCES users (id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_station_resv
    ON station_reservations (venue_id, reservation_date, status);
