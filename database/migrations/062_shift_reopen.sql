-- 062: Buka Kembali Shift (Reopen) + jejak audit.
-- Admin/HO boleh membuka shift yang sudah ditutup utk koreksi, lalu tutup lagi.
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS reopened_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS shift_reopen_logs (
    id             SERIAL PRIMARY KEY,
    shift_id       INTEGER,               -- tak pakai FK: shift bisa saja dihapus
    venue_id       INTEGER,
    reason         TEXT NOT NULL,
    variance_before NUMERIC(15,2),
    counted_before  NUMERIC(15,2),
    deposit_before  NUMERIC(15,2),
    reopened_by    INTEGER REFERENCES users(id),
    reopened_at    TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shift_reopen_logs_venue ON shift_reopen_logs(venue_id);
CREATE INDEX IF NOT EXISTS idx_shift_reopen_logs_at ON shift_reopen_logs(reopened_at);
