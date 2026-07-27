-- 042: riwayat reschedule booking — jejak slot lama → baru (audit di portal).

CREATE TABLE IF NOT EXISTS booking_reschedules (
    id            SERIAL PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    order_item_id INTEGER,
    from_desc     VARCHAR(120),
    to_desc       VARCHAR(120),
    from_price    NUMERIC(15, 2),
    to_price      NUMERIC(15, 2),
    created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reschedule_order ON booking_reschedules (order_id);
