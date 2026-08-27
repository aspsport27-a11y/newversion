-- 061: jejak audit transaksi yg dihapus permanen dari Riwayat Transaksi.
-- Snapshot (order asli sudah tak ada). Penting utk DP hangus yg ikut terhapus.
CREATE TABLE IF NOT EXISTS deleted_order_logs (
    id            SERIAL PRIMARY KEY,
    order_number  VARCHAR(30) NOT NULL,
    venue_id      INTEGER,
    customer_name VARCHAR(100),
    status_before VARCHAR(10),
    total_amount  NUMERIC(15,2) DEFAULT 0,
    forfeited_dp  NUMERIC(15,2) DEFAULT 0,
    deleted_by    INTEGER REFERENCES users(id),
    deleted_at    TIMESTAMP DEFAULT now(),
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_deleted_order_logs_venue ON deleted_order_logs(venue_id);
CREATE INDEX IF NOT EXISTS idx_deleted_order_logs_at ON deleted_order_logs(deleted_at);
