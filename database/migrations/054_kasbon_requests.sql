-- 054: pengajuan kasbon dgn approval HO. Begitu disetujui, sistem otomatis
-- menulis ke data karyawan: catat 'advance' di employee_debts (saldo naik) +
-- set employees.kasbon_installment (cicilan/bulan). Payroll lalu memotong
-- otomatis (min(cicilan, saldo) tiap gajian) — mekanisme lama, tak berubah.
CREATE TABLE IF NOT EXISTS kasbon_requests (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    venue_id INTEGER REFERENCES venues(id) ON DELETE SET NULL,
    amount NUMERIC(15,2) NOT NULL,
    months INTEGER NOT NULL,
    installment NUMERIC(15,2) NOT NULL,       -- dihitung = ceil(amount / months)
    note VARCHAR(200),
    status VARCHAR(12) NOT NULL DEFAULT 'submitted',  -- submitted|approved|rejected
    created_by INTEGER REFERENCES users(id),
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kasbon_req_venue_status
    ON kasbon_requests (venue_id, status);
