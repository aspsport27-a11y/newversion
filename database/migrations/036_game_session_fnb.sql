-- ============================================
-- Migration 036 — game_session_fnb (F&B dipesan di tengah sesi Station Gaming)
-- Sebelumnya F&B tambahan cuma disimpan di keranjang lokal dialog (client) &
-- baru dikirim saat STOP & Bayar — kalau kasir tutup dialog di tengah jalan,
-- pesanan hilang. Padahal customer sering pesan makanan sambil main, kasir
-- entry biar tak lupa, baru dibayar sekalian di akhir. Tabel ini menyimpan
-- pesanan itu menempel ke sesi (spt topup/addon) supaya awet.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

CREATE TABLE IF NOT EXISTS game_session_fnb (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    name_snapshot VARCHAR(120) NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_game_session_fnb_session ON game_session_fnb(session_id);

COMMIT;
