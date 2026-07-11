# Hutang Teknis (Backlog)

Daftar hal yang sengaja ditunda. Kerjakan setelah fitur inti beres.

## 1. Integrasi BRIAPI QRIS (auto-konfirmasi) — DITUNDA
**Status:** provider `bri_qris_mpm` di `backend/app/pos/services.py` masih **stub** —
pembayaran QRIS tercatat `pending` dan **tidak** otomatis dikonfirmasi.

**Yang perlu dibangun nanti:**
- MPM Dinamis (generate QR nominal terkunci per transaksi) via BRIAPI (standar SNAP BI: tanda tangan RSA + access token)
- MPM Notifikasi (webhook) → endpoint `POST /api/pos/webhook/bri` untuk auto-set payment `paid` + jalankan `_apply_payment`
- Sandbox dulu → production

**Prasyarat dari user:** registrasi BRIAPI (client id/secret, merchant/terminal ID QRIS), dokumen "View More" MPM Dinamis & Notifikasi.

**Dampak sekarang:** QRIS di POS bisa dipilih tapi statusnya pending (belum lunas). Operasional bisa jalan penuh dengan **cash** dulu.

---

## Lain-lain
- Struk thermal fisik — sesuaikan driver/model printer (58/80mm). Saat ini struk sudah HTML + print CSS 58mm.
