# Integrasi BRIAPI QRIS (SNAP BI)

Status: **kode selesai & teruji, menunggu kredensial BRI.** Tanpa kredensial,
QRIS otomatis kembali ke perilaku lama (payment `pending`, konfirmasi manual) —
jadi aman dibiarkan sampai BRI siap.

## 1. Yang harus diisi di `.env` backend

```bash
BRI_BASE_URL=https://sandbox.partner.api.bri.co.id   # prod: https://partner.api.bri.co.id
BRI_CLIENT_ID=...          # consumer key (dipakai sbg X-CLIENT-KEY)
BRI_CLIENT_SECRET=...      # consumer secret (tanda tangan simetris)
BRI_PARTNER_ID=...         # X-PARTNER-ID
BRI_CHANNEL_ID=...         # CHANNEL-ID
BRI_PRIVATE_KEY_PATH=/opt/aspsport-backend/secrets/bri_private.pem
BRI_MERCHANT_ID=...        # merchant QRIS
BRI_TERMINAL_ID=...        # terminal QRIS (opsional)
BRI_QR_TTL_SECONDS=900     # masa berlaku QR (default 15 menit)
```

Integrasi baru menyala kalau **client id, client secret, partner id, private
key, dan merchant id** semuanya terisi (`briapi.is_configured()`).

### Private key
Buat pasangan kunci RSA, daftarkan **public key**-nya ke portal BRIAPI:

```bash
openssl genrsa -out bri_private.pem 2048
openssl rsa -in bri_private.pem -pubout -out bri_public.pem
```

Simpan private key di luar repo, permission ketat (`chmod 600`), lalu arahkan
`BRI_PRIVATE_KEY_PATH` ke sana. **Jangan** commit file ini.

### URL webhook yang didaftarkan ke BRI
```
https://pos.aspsports.id/api/pos/webhook/bri
```

## 2. Alur

```
Kasir pilih QRIS
  → POST /api/pos/orders/<id>/pay {method: "qris"}
  → backend: generate QR MPM Dinamis ke BRI (nominal terkunci)
  → payment tersimpan 'pending' + qr_content + external_id
  → POS tampilkan QR (QrisDialog), polling status tiap 3 detik
Customer scan & bayar
  → BRI kirim notifikasi ke POST /api/pos/webhook/bri
  → backend verifikasi → payment 'paid' → _apply_payment (order + shift)
  → POS lihat status 'paid' → cetak struk
```

Kalau webhook telat/tidak sampai, kasir bisa tekan **"Cek status"** →
`POST /api/pos/payments/<id>/qris/sync` → backend bertanya langsung ke BRI.

## 3. Pengamanan webhook (endpoint publik, pintu masuk uang)

Berlapis, semuanya sudah diuji:

| Lapis | Perilaku |
|---|---|
| Tanda tangan HMAC-SHA512 | Wajib valid; body diubah 1 byte pun tanda tangan gugur → 401 |
| Kesegaran timestamp | Toleransi 10 menit → notifikasi lama tak bisa diputar ulang → 400 |
| Kunci baris (`FOR UPDATE`) | Webhook & polling tak bisa sama-sama mengkredit |
| Cek nominal | Nominal notifikasi harus sama persis dgn payment → kalau beda, ditolak |
| Idempoten | `paid_notified_at` + cek status; kiriman ulang tidak menambah uang |

Status BRI yang tak dikenal selalu diperlakukan **pending** (uang tidak diakui
sampai benar-benar terbukti lunas), bukan paid.

## 4. Kolom baru (`payments`, migrasi 039)

| Kolom | Guna |
|---|---|
| `qr_content` | String QR mentah dari BRI (dirender jadi gambar di POS) |
| `qr_expires_at` | Batas berlaku QR (UTC) |
| `external_id` | `partnerReferenceNo`, UNIQUE — kunci cocokkan notifikasi |
| `bri_reference_no` | Nomor transaksi sisi bank |
| `paid_notified_at` | Penanda idempoten notifikasi lunas |

`external_id` memakai komponen acak (`secrets.token_hex`) supaya nomor
referensi transaksi lain tidak bisa ditebak orang luar.

## 5. Yang WAJIB dicek saat kredensial sudah ada

Kode ini belum pernah memanggil server BRI sungguhan. Sebelum dipakai di venue:

1. **Sandbox dulu.** Ambil access token → pastikan tanda tangan asimetris diterima.
2. **Generate QR** → cek nama field respons. Kode membaca `qrContent`, fallback
   ke `qrString`/`qrImage`; kalau BRI memakai nama lain, sesuaikan di
   `app/pos/briapi.py` → `generate_qr()`.
3. **Skema tanda tangan notifikasi** — ini yang paling perlu dipastikan. Dokumen
   "MPM Notifikasi" tiap merchant bisa berbeda soal apakah access token ikut
   masuk string tanda tangan. `verify_notification()` sudah mencoba dua varian
   (dengan & tanpa token), tapi cocokkan dengan dokumen resmi Anda.
4. **Kode status** — `normalize_status()` memetakan `latestTransactionStatus`
   SNAP (00=sukses, 01/03=pending, 02/05/06=gagal). Verifikasi dengan dokumen.
5. Baru pindah ke production URL.

## 6. Catatan operasional

- Uang QRIS masuk **rekening bank**, bukan laci kas — setoran tunai shift tidak
  terpengaruh. Yang bertambah hanya `total_qris_sales` shift.
- Kalau konfirmasi datang setelah shift ditutup, pembayaran tetap dibukukan ke
  shift yang melakukan penjualan (supaya laporan konsisten dgn tanggal order)
  dan dicatat peringatan di log.
- Rekonsiliasi QRIS di menu **Kas & Bank** tetap berjalan seperti biasa
  (bandingkan total POS vs mutasi bank).
