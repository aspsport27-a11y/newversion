-- 063: Penyesuaian shift cepat (+/- per metode) oleh Admin/HO — jejak audit.
-- Penyesuaian dibuat sbg order+payment back-date (tgl shift) agar Laporan Shift
-- & Laporan Penjualan konsisten. Tabel ini menyimpan ringkasan tiap penyesuaian.
CREATE TABLE IF NOT EXISTS shift_adjust_logs (
    id             SERIAL PRIMARY KEY,
    shift_id       INTEGER,
    venue_id       INTEGER,
    cash_delta     NUMERIC(15,2) DEFAULT 0,
    qris_delta     NUMERIC(15,2) DEFAULT 0,
    transfer_delta NUMERIC(15,2) DEFAULT 0,
    note           TEXT NOT NULL,
    order_number   VARCHAR(30),
    adjusted_by    INTEGER REFERENCES users(id),
    adjusted_at    TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shift_adjust_logs_venue ON shift_adjust_logs(venue_id);
CREATE INDEX IF NOT EXISTS idx_shift_adjust_logs_at ON shift_adjust_logs(adjusted_at);
