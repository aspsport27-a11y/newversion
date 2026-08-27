-- 064: Event (borong semua lapangan) — turnamen/sewa besar yang mengunci
-- seluruh lapangan venue pada rentang tanggal + jam tertentu. Member yang
-- bentrok dipindah jadwal. Uang sewa lewat order biasa (order_id).
CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    venue_id    INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    name        VARCHAR(120) NOT NULL,
    renter      VARCHAR(120),
    phone       VARCHAR(30),
    date_from   DATE NOT NULL,
    date_to     DATE NOT NULL,
    start_time  TIME NOT NULL,
    end_time    TIME NOT NULL,
    price       NUMERIC(15,2) NOT NULL DEFAULT 0,
    order_id    INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    status      VARCHAR(12) NOT NULL DEFAULT 'active',  -- active|cancelled
    notes       TEXT,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_venue_dates ON events(venue_id, date_from, date_to);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
