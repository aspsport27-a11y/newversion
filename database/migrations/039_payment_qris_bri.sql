-- ============================================
-- Migration 039 — kolom QRIS dinamis (BRIAPI) pada payments
--
-- Menyimpan jejak satu transaksi QRIS MPM Dinamis:
--   qr_content       string QR mentah dari BRI (dirender jadi gambar QR di POS)
--   qr_expires_at    batas waktu QR berlaku (UTC, seperti kolom waktu lain)
--   external_id      partnerReferenceNo/X-EXTERNAL-ID — unik per transaksi,
--                    dipakai mencocokkan notifikasi (webhook) BRI ke payment ini
--   bri_reference_no referenceNo dari BRI (nomor transaksi di sisi bank)
--   paid_notified_at kapan notifikasi lunas diterima — penanda idempoten supaya
--                    webhook yang dikirim ulang tidak menambah uang dua kali
--
-- external_id di-UNIQUE: pertahanan lapis DB terhadap dobel-kredit kalau ada
-- balapan (webhook + polling datang bersamaan). NULL tetap boleh berulang
-- (pembayaran cash/transfer tidak punya external_id).
--
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;

ALTER TABLE payments ADD COLUMN IF NOT EXISTS qr_content       TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS qr_expires_at    TIMESTAMP;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS external_id      VARCHAR(64);
ALTER TABLE payments ADD COLUMN IF NOT EXISTS bri_reference_no VARCHAR(64);
ALTER TABLE payments ADD COLUMN IF NOT EXISTS paid_notified_at TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_external_id
    ON payments (external_id) WHERE external_id IS NOT NULL;

-- pencarian saat notifikasi BRI masuk (cocokkan lewat nomor referensi bank)
CREATE INDEX IF NOT EXISTS ix_payments_bri_reference_no
    ON payments (bri_reference_no) WHERE bri_reference_no IS NOT NULL;

COMMIT;
