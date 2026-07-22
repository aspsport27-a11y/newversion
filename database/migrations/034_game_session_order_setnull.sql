-- ============================================
-- Migration 034 — game_sessions.order_id ON DELETE SET NULL
-- Hapus permanen order (yg statusnya void) via /admin/orders/<id> gagal
-- dgn 500 kalau order itu terhubung ke GameSession (Station Gaming) —
-- FK-nya tadinya NO ACTION jadi Postgres nolak hapus order selama masih
-- direferensikan. Diubah jadi SET NULL: sesi station tetap ada sbg riwayat,
-- cuma order_id-nya jadi kosong kalau order-nya dihapus.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE game_sessions DROP CONSTRAINT IF EXISTS game_sessions_order_id_fkey;
ALTER TABLE game_sessions
    ADD CONSTRAINT game_sessions_order_id_fkey
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL;

COMMIT;
