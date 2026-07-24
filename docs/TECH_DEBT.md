# Hutang Teknis (Backlog)

Daftar hal yang sengaja ditunda. Kerjakan setelah fitur inti beres.

## 1. Integrasi BRIAPI QRIS (auto-konfirmasi) — KODE SELESAI, MENUNGGU KREDENSIAL
**Status (2026-07-24):** sudah **dibangun & teruji**. Lihat `docs/BRIAPI_QRIS.md`
untuk detail lengkap (konfigurasi, alur, pengamanan, daftar cek sandbox).

**Yang sudah ada:**
- `app/pos/briapi.py` — client SNAP BI (tanda tangan asimetris RSA-SHA256 utk access
  token, simetris HMAC-SHA512 utk transaksi, cache token, generate QR, query status)
- Provider `bri_qris_mpm` bikin QR MPM Dinamis (nominal terkunci)
- Webhook `POST /api/pos/webhook/bri` — verifikasi tanda tangan, anti replay,
  cek nominal, kunci baris, idempoten (25 uji integrasi lulus)
- Polling status + tombol "Cek status" di POS, dialog QR dgn hitung mundur
- Migrasi 039 (kolom QRIS di `payments`)

**Sisa prasyarat dari user:** kredensial BRIAPI (client id/secret, private key
terdaftar, merchant/terminal ID) + dokumen "MPM Notifikasi" untuk memastikan
skema tanda tangan webhook & nama field respons.

**Dampak sekarang:** kredensial belum diisi → `briapi.is_configured()` False →
QRIS otomatis kembali ke perilaku lama (pending, konfirmasi manual). Aman, tidak
mengubah operasional yang sedang jalan.

---

## Lain-lain
- Struk thermal fisik — sesuaikan driver/model printer (58/80mm). Saat ini struk sudah HTML + print CSS 58mm.
