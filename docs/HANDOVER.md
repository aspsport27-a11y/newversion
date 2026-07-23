# ASP Sport System — Handover

Dokumen serah-terima: status sistem, arsitektur, operasional, dan sisa pekerjaan.
Terakhir diperbarui: 2026-07-22.

---

## 1. Ringkasan

Sistem manajemen terintegrasi multi-venue olahraga (13 unit: lapangan bola, mini soccer,
waterpark, futsal, padel, esport/Station Gaming). **POS kasir + admin backoffice + halaman
jadwal publik**, live & dipakai.

| | URL | Untuk |
|---|-----|-------|
| **Admin** | https://portal.aspsports.id | Super Admin, HO, Manager, Admin Area (backoffice) — login lain (staff/kasir) ditolak |
| **POS** | https://pos.aspsports.id | Kasir & Manager (login PIN/username), transaksi |
| **Jadwal publik** | https://jadwal.aspsports.id | Customer umum, tanpa login — cek jadwal lapangan/harga, booking via WhatsApp |

Server VPS IPv4 **31.97.66.93** (Hostinger/sejenis). Semua ber-SSL (Let's Encrypt, auto-renew).

---

## 2. Arsitektur

```
Internet ─HTTPS─► Nginx ─┬─ portal.aspsports.id → SPA admin (Vue 3)
                         └─ pos.aspsports.id     → SPA POS (Vue 3)
                                  │  /api/*  (reverse proxy)
                                  ▼
                         Gunicorn (Flask) 127.0.0.1:8000
                                  ▼
                         PostgreSQL 16 — DB "venue_system"
```

- **Backend:** Python Flask (app factory), SQLAlchemy, JWT. Blueprint per modul.
- **Frontend:** Vue 3 + Vite + Pinia + Vue Router + Tailwind (+ Chart.js di admin).
- **Satu backend, TIGA frontend (admin/POS/publik), satu DB.**

### Lokasi di server
| Apa | Path |
|-----|------|
| Backend | `/opt/aspsport-backend` (venv, service `aspsport-backend`, user `aspsport`) |
| Frontend admin | `/opt/aspsport-frontend` → deploy ke `/var/www/portal.aspsports.id/html` |
| Frontend POS | `/opt/aspsport-pos-frontend` → deploy ke `/var/www/pos.aspsports.id/html` |
| Frontend jadwal publik | `/opt/aspsport-public-frontend` → deploy ke `/var/www/jadwal.aspsports.id/html` |
| Kredensial DB | `/root/venue_system.db.env` |
| Kredensial admin | `/root/aspsport_admin.txt` |
| Upload bukti (op/PO/absen/bukti transfer) | `/opt/aspsport-uploads/` (subfolder: `oprequests`, `attendance`, `payment_proof`) |
| Repo lokal | `/root/aspsport-repo` |

---

## 3. Repo & deploy

- **GitHub:** github.com/aspsport27-a11y/newversion (monorepo: `backend/` `frontend-admin/`
  `frontend-pos/` `database/` `docs/`).
- **Push tanpa token:** SSH deploy key di VPS (`/root/.ssh/github_aspsport`, remote SSH).
  Cukup `cd /root/aspsport-repo && git add -A && git commit -m "…" && git push`.

### Alur deploy perubahan
```bash
# Backend: edit /opt/aspsport-backend/app/... lalu:
systemctl restart aspsport-backend
# Frontend admin:
cd /opt/aspsport-frontend && npm run build
cp -a dist/. /var/www/portal.aspsports.id/html/ && chown -R www-data:www-data /var/www/portal.aspsports.id
# Frontend POS: sama, folder /opt/aspsport-pos-frontend → /var/www/pos.aspsports.id/html
# Lalu sync ke repo (rm -rf $STAGE/backend/app; cp -a ...) + git push
```

### Operasional
- Status/log backend: `systemctl status aspsport-backend` · `journalctl -u aspsport-backend -f`
- DB: `source /root/venue_system.db.env; PGPASSWORD=$DB_PASSWORD psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME`
- Migrasi baru: taruh di `database/migrations/NNN_*.sql`, jalankan via psql.

---

## 4. Peran (roles) & akses

6 role (`app/security.py` `VALID_ROLES`): `admin`, `head_office`, `manager_unit`, `admin_unit`,
`staff` (Kasir), `staff_other` (Ass. Manager/SPV & Staff — absen doang, PIN, TAK bisa POS).

| Role | Login **Portal** | Login **POS** | Akses |
|------|:---:|:---:|-------|
| `admin` | ✅ | ❌ | Semua (superuser, bypass RBAC) |
| `head_office` | ✅ | ❌ | Semua backoffice (approve, bayar, kelola) |
| `manager_unit` | ✅ | ✅ | Terbatas venue-nya: Dashboard, Karyawan, Operasional (+kategori beban venue sendiri), Procurement, Payroll, Booking, Kategori Station Gaming (kalau venue esport) |
| `admin_unit` | ✅ | ❌ | Terbatas area-nya: produk/lapangan/promo |
| `staff` (Kasir) | ❌ | ✅ | Transaksi POS saja |
| `staff_other` | ❌ | ❌ | Absen saja (menu Absen di POS, tanpa masuk kasir) |

RBAC configurable via tabel `role_permissions` (`app/perms.py` katalog + UI Hak Akses,
admin-only). **Penting:** `DEFAULT_GRANTS` di `perms.py` cuma dipakai `seed_defaults()` (sekali,
bila tabel kosong) — izin baru ke role yg sudah ada HARUS lewat migration SQL manual
(`INSERT INTO role_permissions ...`), tidak otomatis retroaktif.

**Perilaku permission di frontend:** `auth.permissions` disimpan di localStorage, di-refresh
tiap kali app dimuat (`DashboardLayout.vue` — always call `fetchMe()`, bukan cuma kalau kosong,
supaya perubahan RBAC langsung berlaku tanpa perlu logout manual).

Karyawan = master; sebagian dibuatkan **akun login** (users.employee_id) via menu Karyawan.
Menu admin otomatis tersaring per role.

---

## 5. Modul — status

| Modul | Status | Backend | Frontend |
|-------|--------|---------|----------|
| POS (produk/tiket, booking, DP/pelunasan, no-show, promo, shift+rekonsiliasi) | ✅ live | `app/pos` | pos.aspsports.id |
| Pembayaran POS: **Cash / QRIS (pending) / Transfer Bank** (wajib upload bukti) | ✅ | `app/pos` | pos.aspsports.id |
| Station Gaming (esport) — sewa per jam, hitung mundur, add-on, alarm waktu habis | ✅ | `app/stations`, `app/pos` (topup/addon/stop) | pos.aspsports.id |
| Tarif lapangan per rentang jam (`facility_rate_rules`, mis. malam beda tarif) | ✅ | `app/pos/models.py` (`facility_rate_for_hour`) | Lapangan & Tiket (tombol "Tarif") |
| Halaman Jadwal Publik (cek slot kosong + harga, tanpa login, CTA booking via WA) | ✅ | `app/public` (rate-limited) | jadwal.aspsports.id |
| Absensi (GPS + reverse-geocode Nominatim, foto, filter nama, export Excel) | ✅ | `app/admin`, `app/pos` (attendance) | Absensi |
| Promo (harga/persen/BOGO + periode) | ✅ | `app/pos/promos.py` | Promo |
| Admin master (venue, produk, lapangan, kasir/terminal, booking, laporan) | ✅ | `app/admin` | portal |
| Karyawan + Kasbon (cicilan) | ✅ | `app/admin` (employees) | Karyawan |
| Operasional & Budget (approval HO, plafon, bukti, kategori beban per-venue) | ✅ | `app/ops` | Operasional |
| Procurement (PO, supplier, terima→stok, reorder) | ✅ | `app/proc` | Procurement |
| Payroll (generate, potong kasbon, slip) | ✅ | `app/payroll` | Payroll |
| Kas & Bank / Treasury (rekening, Kas Fisik HO pool, setoran, QRIS recon, rekonsiliasi bank) | ✅ | `app/treasury` | Kas & Bank |
| Financial Report + Laporan Manajemen (laba-rugi, arus kas, saldo kas per venue) | ✅ | `app/financial` | Laporan Bisnis/Manajemen |

### Alur kunci
- **POS bayar:** cash (lunas otomatis, potong stok) / QRIS (pending — nunggu BRIAPI) / **Transfer
  Bank** (wajib upload bukti/screenshot, langsung dianggap lunas spt cash — lihat `Payment.proof_image`,
  endpoint lihat bukti `GET /admin/payments/<id>/proof`, auth-gated spt foto absen).
- **Booking:** DP (bayar sebagian) → pelunasan (menu "Order Belum Bayar" di POS, tangkap status
  `open`+`partial`, bukan cuma booking) → atau no-show (batal, DP hangus). Slot anti-bentrok
  (termasuk yg tutup tengah malam 00:00 — dihitung sbg "jam ke-24", lihat §9).
- **Station Gaming:** mulai sesi dgn paket waktu awal (default 60 menit, tarif otomatis) → jam
  hitung mundur sisa paket (hitung maju kalau belum pernah ada "Tambah Waktu") → alarm bunyi
  kalau lewat waktu → stop & bayar (harga FINAL selalu dari elapsed sungguhan di server, hitung
  mundur cuma info visual, bukan sumber harga).
- **Kas Fisik HO:** shift ditutup → kas fisik terkumpul di pool "Kas Fisik HO" (bukan langsung ke
  Holding) → bisa dipakai opex dulu → baru disetor final ke rekening Holding. Field "Setoran ke HO"
  di dialog Tutup Shift otomatis ikut "Uang tunai dihitung" (dulu opsional & sering kosong,
  bikin kas "hilang" dr antrean).
- **Operasional:** Manager ajukan (kategori beban bisa venue sendiri sejak migrasi 030+031) →
  HO approve → cairkan (pilih sumber dana). Plafon budget vs realisasi.
- **Procurement:** Unit buat PO → unit approve → terima (stok masuk) → HO bayar (sumber dana).
- **Payroll:** Manager generate (auto: pokok+tunjangan−kasbon−potongan) → HO approve → bayar (potong kasbon dieksekusi).
- **Financial Report:** agregasi basis kas — pendapatan (payments diterima) − beban (operasional cair + PO dibayar + payroll dibayar) = laba/rugi; + snapshot saldo kas. `GET /api/financial/report?from=&to=&venue_id=`. Manager dibatasi venue-nya.

---

## 6. Data model

- Base: `database/schema.sql` (17 tabel awal). Migrasi `002`–`034` di `database/migrations/`
  (idempotent, aman dijalankan ulang). Highlight migrasi terbaru: `027` Kas Fisik HO, `028`-`029`
  lokasi+alamat absensi, `030`-`031` kategori beban per-venue, `032` tarif lapangan per jam,
  `033` metode bayar transfer + bukti, `034` fix FK `game_sessions.order_id` → `ON DELETE SET NULL`.
- **Tabel usang** (digantikan, boleh dibersihkan nanti): `bookings`, `daily_sales`,
  `inventory`, `stock_transactions`, `procurement_requests`, `procurement_items`,
  `payroll` (lama), `operational_requests`/`budget_allocation` (lama), `departments`, `approvals`, `audit_logs`.

---

## 7. Data uji / demo (bisa dihapus/diganti)

- Kasir POS: `kasir1`/PIN 1234 (V001, terminal T-V001-01), `kasirwp`/PIN 5678 (V007, terminal BMW)
- Manager: `andi`/`andimanager1` (V007)
- Karyawan: Andi, Sari (V007, Sari punya kasbon+cicilan), Budi (V001)
- Produk: FB001 Aqua, FB002 Pop Mie, FB003 Gorengan (V001); tiket TKT-WP-D/A (V007)
- Promo, lapangan (Lapangan A/B), supplier (CV Sumber Minuman), rekening (Holding, Waterpark), dll.

---

## 8. Sisa pekerjaan / backlog

1. ~~**Financial Report**~~ — ✅ SELESAI (`app/financial`, commit 9836a56).
2. **BRIAPI QRIS** (hutang teknis, `docs/TECH_DEBT.md`) — **masih prioritas utama tersisa**. QRIS
   auto-konfirmasi (MPM Dinamis + Notifikasi/webhook). Sekarang QRIS di POS = pending. Transfer
   Bank (manual, bukti wajib) sudah jadi alternatif non-cash yg langsung lunas sementara ini.
3. **Nonaktifkan venue tak terpakai** — user minta, belum dieksekusi (V002-006, V008-012 kosong).
4. **Bersihkan tabel usang** (lihat §6).
5. **Data asli** — ganti data demo dengan data operasional nyata (produk, karyawan, rekening, saldo awal).
   Beberapa venue (GYSF, W Arena, dll) sudah mulai ada transaksi riil dr testing — cek dulu sebelum
   hapus massal data, jangan asumsikan semua masih demo.
6. **Struk thermal fisik** — sesuaikan model printer.
7. **Nomor telepon venue** — kolom `Venue.phone` masih placeholder (`0812`, `0813`, dst) di banyak
   venue → tombol WA di halaman jadwal publik belum bisa dites end-to-end sampai diisi nomor asli.
8. **⭐ "Radar Operasional" (fitur AI) — DIREKOMENDASIKAN, baru tahap diskusi (2026-07-23).**
   Arah AI yg disepakati bareng owner: AI TIDAK menaikkan omzet, dampak nyatanya di **visibilitas &
   kontrol** utk owner yg pegang belasan venue jarak jauh (pain: takut kebocoran tak terpantau +
   capek cek laporan manual). Konsep: sapu data harian → tandai kejanggalan → urut per risiko
   (rupiah) → AI ringkas jd bahasa manusia. **Prinsip:** sinyal deterministik (SQL) = 70% nilai;
   AI cuma lapisan tipis keterbacaan + Q&A; **AI menunjuk, manusia memutuskan**; framing "perlu
   dicek" bukan "curang". **Sinyal (semua dr data existing):** selisih kas berulang per kasir, shift
   belum disetor, hapus-permanen order/payment, void/diskon tak wajar, omzet venue turun tajam vs
   rata2 7hr, venue nol transaksi di jam buka, sesi gaming charge 0/instan, stok susut tanpa jual,
   kasir transaksi tanpa absen, lokasi absen jauh dr venue. **3 fase:** (1) Radar deterministik
   (panel Dashboard, tanpa AI) → (2) lapisan AI ringkas+Q&A (bangun di atas "Ask AI" existing:
   `app/ai/routes.py`+`AskAiDialog.vue`) → (3) push ke channel (email/Telegram/WA). Kerjakan Fase 1
   dulu walau "belum AI" — AI tak berguna tanpa sinyal. STATUS: nunggu keputusan owner soal sinyal
   prioritas + channel.

---

## 9. Catatan penting

- Password admin & PIN demo tersimpan di `/root/aspsport_admin.txt`. Ganti sebelum go-live nyata.
- Backup: private key deploy (`/root/.ssh/github_aspsport`) & DB (`pg_dump venue_system`).
- QRIS **belum** settle otomatis (BRIAPI). Jangan andalkan QRIS untuk transaksi final sampai itu beres.

### Gotcha teknis yg sudah ketemu & diperbaiki (baca sebelum ubah area terkait)
- **Timezone**: backend simpan/kirim datetime **UTC tanpa suffix `Z`**. Browser salah baca itu
  sbg waktu lokal kalau langsung di-`new Date(str)`. Frontend WAJIB pakai `utils/datetime.js`
  → `parseUTC(str)` (nambah `Z` dulu) di semua tempat yg tampilkan jam, bukan `new Date()` langsung.
- **Jam tutup tengah malam (00:00)**: SELALU perlakukan sbg "jam ke-24" (bukan jam ke-0), baik di
  generate slot, hitung durasi booking, maupun cek bentrok jadwal — kalau tidak, hasilnya kosong/
  durasi negatif/deteksi bentrok gagal total. Pola ini dipakai konsisten di `BookingDialog.vue`,
  `app/public/routes.py` (`_end_dt`), `app/pos/services.py` (`_hours_between`, `is_slot_available`).
- **Nomor order (`generate_order_number`)**: pakai nomor urut TERBESAR yg sudah ada + 1, BUKAN
  `COUNT(*) + 1` — count based bisa tabrakan (`UniqueViolation`) begitu ada order yg dihapus permanen
  (gap di tengah nomor urut, count turun tapi nomor besar tetap hidup).
- **RBAC baru tak retroaktif**: nambah permission ke role yg sudah eksis via `DEFAULT_GRANTS` di
  `perms.py` TIDAK otomatis berlaku — wajib migration SQL `INSERT INTO role_permissions`. Frontend
  jg cache `permissions` di localStorage; `DashboardLayout.vue` refresh tiap app dimuat (bukan cuma
  kalau kosong) spy user aktif tak perlu logout manual.
- **Harga booking/Station Gaming dihitung ulang di SERVER**, bukan dipercaya dr client — kalau nambah
  logika harga baru (rate rules, dll), pastikan backend (`facility_booking_price`, `create_order`,
  `station_stop`) yg jadi sumber kebenaran; frontend cuma replikasi utk preview, boleh beda platform
  tapi hasil akhirnya harus sama.
- **FK tanpa `ondelete`** bisa bikin fitur "Hapus Permanen" gagal 500 kalau row itu direferensikan
  tabel lain (contoh nyata: `game_sessions.order_id`, diperbaiki jadi `ON DELETE SET NULL` migrasi 034).
  Kalau bikin fitur delete baru, cek dulu FK apa saja yg mengarah ke tabel itu.
- **Endpoint POS vs Admin**: aksi sensitif (mis. cancel order) yg ada di KEDUA sisi (POS & admin)
  harus DUA-DUANYA dicek permission-nya secara independen — jangan andalkan "UI-nya kan tak ada
  tombolnya" sbg satu-satunya proteksi (endpoint POS `/orders/<id>/cancel` sempat tanpa cek izin
  sama sekali, ketemu & diperbaiki di sesi 2026-07-22).
