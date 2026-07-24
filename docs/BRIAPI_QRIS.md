# Integrasi BRIAPI QRIS (SNAP BI)

> **Status handoff (2026-07-24):** kode selesai & teruji. Tes ke sandbox BRI:
> **access token B2B SUKSES** (rantai auth terbukti), **path generate QR = v1.1**
> (sudah diperbaiki). Berhenti di validasi header — butuh **3 nilai dari BRI**
> yang tak bisa ditebak:
> 1. **X-PARTNER-ID** (numerik, khusus app kita) → `BRI_PARTNER_ID`
> 2. **Merchant ID + Terminal ID** QRIS (onboarding cabang) → `BRI_MERCHANT_ID/BRI_TERMINAL_ID`
> 3. **Public key BRI** (verifikasi webhook) → `BRI_PUBLIC_KEY_PATH` + daftarkan callback
>    `https://pos.aspsports.id/api/pos/webhook/bri`
>
> Kontak BRI: briapi@bri.co.id / briapi@corp.bri.co.id / RM cabang.
> Client ID sandbox & private key sudah tersimpan di server. Integrasi OFF
> (partner/merchant id kosong) → QRIS POS aman, berperilaku spt lama.
> Melanjutkan: isi 3 nilai ke `.env`, restart backend, tes `briapi.generate_qr`.

---

## 1. Yang harus diisi di `.env` backend

```bash
BRI_BASE_URL=https://sandbox.partner.api.bri.co.id   # prod: https://partner.api.bri.co.id
BRI_CLIENT_ID=...          # consumer key (dipakai sbg X-CLIENT-KEY)
BRI_CLIENT_SECRET=...      # consumer secret (tanda tangan simetris)
BRI_PARTNER_ID=...         # X-PARTNER-ID
BRI_CHANNEL_ID=...         # CHANNEL-ID
BRI_PRIVATE_KEY_PATH=/opt/aspsport-backend/secrets/bri_private.pem
BRI_PUBLIC_KEY_PATH=/opt/aspsport-backend/secrets/bri_public_bri.pem  # public key MILIK BRI
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
| Tanda tangan RSA BRI | SHA256withRSA atas `clientId\|timestamp`, diverifikasi dgn public key BRI → 401 kalau gagal |
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
3. **Public key BRI** — minta ke BRI, simpan, arahkan `BRI_PUBLIC_KEY_PATH`.
   Tanpa ini webhook SELALU ditolak (sengaja: lebih baik tolak daripada salah kredit).
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


## 7. ⚠️ Kelemahan skema notifikasi BRI yang harus diketahui

Tanda tangan notifikasi BRI hanya mencakup `clientId|timestamp` — **isi body tidak
ikut ditandatangani**. Artinya tanda tangan yang valid TIDAK membuktikan isi pesan
asli. Karena itu pemeriksaan lain di webhook bukan pelengkap, melainkan pengaman
utama:

- nominal notifikasi **wajib** sama persis dengan nominal payment;
- payment dicari lewat `external_id` yang mengandung komponen acak (tak bisa ditebak);
- baris dikunci `FOR UPDATE` + idempoten.

**Jangan pernah** melonggarkan pemeriksaan itu dengan alasan "kan sudah ada tanda
tangan". Skenario terburuk yang tersisa: pihak yang bisa mencegat satu notifikasi
sah bisa mengulanginya dalam 10 menit — dan itu pun hanya mengonfirmasi ulang
transaksi yang memang sudah ada dengan nominal yang sama persis, yang sudah
ditangkap oleh idempotensi.

## 8. Koreksi yang sudah diterapkan (2026-07-24)

Setelah membandingkan dengan dokumentasi resmi BRI, tiga hal diperbaiki:

| Semula (salah) | Sekarang (sesuai dokumen BRI) |
|---|---|
| `/v1.0/qr/qr-mpm-generate` | `/v1.0/qr-dynamic-mpm/qr-mpm-generate-qr` |
| `X-EXTERNAL-ID` = `ASP…` (alfanumerik) | numerik saja (`new_request_id()`); header juga dikirim dalam ejaan `X-EXTRENAL-ID` sesuai salah ketik di dokumen BRI |
| Verifikasi webhook HMAC-SHA512 + client secret | RSA SHA256 + **public key BRI** |
