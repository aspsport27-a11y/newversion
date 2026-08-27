-- 065: penanda "sudah dihubungi" untuk member/pelanggan yang terdampak event
-- (perlu dipindah jadwal). Satu baris = 1 order terdampak yang sudah dikontak.
CREATE TABLE IF NOT EXISTS event_contacts (
    id           SERIAL PRIMARY KEY,
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    order_id     INTEGER NOT NULL,
    contacted_by INTEGER REFERENCES users(id),
    contacted_at TIMESTAMP DEFAULT now(),
    UNIQUE (event_id, order_id)
);
CREATE INDEX IF NOT EXISTS idx_event_contacts_event ON event_contacts(event_id);
