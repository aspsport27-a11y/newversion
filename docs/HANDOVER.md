# ASP Sport System — Handover

Dokumen serah-terima: status sistem, arsitektur, operasional, dan sisa pekerjaan.
Terakhir diperbarui: 2026-07-12.

---

## 1. Ringkasan

Sistem manajemen terintegrasi multi-venue olahraga (13 unit: lapangan bola, mini soccer,
waterpark, futsal, padel, esport). **POS kasir + admin backoffice**, live & dipakai.

| | URL | Untuk |
|---|-----|-------|
| **Admin** | https://portal.aspsports.id | Head Office, Manager (backoffice) |
| **POS** | https://pos.aspsports.id | Kasir (login PIN) |

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
- **Satu backend, dua frontend, satu DB.**

### Lokasi di server
| Apa | Path |
|-----|------|
| Backend | `/opt/aspsport-backend` (venv, service `aspsport-backend`, user `aspsport`) |
| Frontend admin | `/opt/aspsport-frontend` → deploy ke `/var/www/portal.aspsports.id/html` |
| Frontend POS | `/opt/aspsport-pos-frontend` → deploy ke `/var/www/pos.aspsports.id/html` |
| Kredensial DB | `/root/venue_system.db.env` |
| Kredensial admin | `/root/aspsport_admin.txt` |
| Upload bukti (op/PO) | `/opt/aspsport-uploads/` |
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

| Role | Akses |
|------|-------|
| `admin` | Semua |
| `head_office` | Semua backoffice (approve, bayar, kelola) |
| `manager_unit` | Terbatas venue-nya: Dashboard, Karyawan, Operasional, Procurement, Payroll (generate/ajukan). Tak bisa bayar/approve keuangan lintas venue |
| `staff` (kasir) | Login POS (PIN), transaksi |

Karyawan = master; sebagian dibuatkan **akun login** (users.employee_id) via menu Karyawan.
Menu admin otomatis tersaring per role.

---

## 5. Modul — status

| Modul | Status | Backend | Frontend |
|-------|--------|---------|----------|
| POS (produk/tiket, booking, DP/pelunasan, no-show, promo, shift+rekonsiliasi) | ✅ live | `app/pos` | pos.aspsports.id |
| Promo (harga/persen/BOGO + periode) | ✅ | `app/pos/promos.py` | Promo |
| Admin master (venue, produk, lapangan, kasir/terminal, booking, laporan) | ✅ | `app/admin` | portal |
| Karyawan + Kasbon (cicilan) | ✅ | `app/admin` (employees) | Karyawan |
| Operasional & Budget (approval HO, plafon, bukti) | ✅ | `app/ops` | Operasional |
| Procurement (PO, supplier, terima→stok, reorder) | ✅ | `app/proc` | Procurement |
| Payroll (generate, potong kasbon, slip) | ✅ | `app/payroll` | Payroll |
| Kas & Bank / Treasury (rekening, setoran, QRIS recon, sumber dana) | ✅ | `app/treasury` | Kas & Bank |
| **Financial Report** | ⏳ **BELUM** (modul terakhir) | — | — |

### Alur kunci
- **POS bayar:** cash (lunas otomatis, potong stok) / QRIS (pending — nunggu BRIAPI).
- **Booking:** DP (bayar sebagian) → pelunasan → atau no-show (batal, DP hangus). Slot anti-bentrok.
- **Operasional:** Manager ajukan → HO approve → cairkan (pilih sumber dana). Plafon budget vs realisasi.
- **Procurement:** Unit buat PO → unit approve → terima (stok masuk) → HO bayar (sumber dana).
- **Payroll:** Manager generate (auto: pokok+tunjangan−kasbon−potongan) → HO approve → bayar (potong kasbon dieksekusi).
- **Kas & Bank:** QRIS→rek venue (HO recon), cash→setor holding, pengeluaran default holding, sapu venue→holding.

---

## 6. Data model

- Base: `database/schema.sql` (17 tabel awal). Migrasi `002`–`011` di `database/migrations/`.
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

1. **Financial Report** (modul terakhir) — laba-rugi & arus kas per venue, gabung semua modul.
2. **BRIAPI QRIS** (hutang teknis, `docs/TECH_DEBT.md`) — QRIS auto-konfirmasi (MPM Dinamis +
   Notifikasi/webhook). Sekarang QRIS di POS = pending. Operasional pakai cash dulu.
3. **Nonaktifkan venue tak terpakai** — user minta, belum dieksekusi (V002-006, V008-012 kosong).
4. **Bersihkan tabel usang** (lihat §6).
5. **Data asli** — ganti data demo dengan data operasional nyata (produk, karyawan, rekening, saldo awal).
6. **Struk thermal fisik** — sesuaikan model printer.

---

## 9. Catatan penting

- Password admin & PIN demo tersimpan di `/root/aspsport_admin.txt`. Ganti sebelum go-live nyata.
- Backup: private key deploy (`/root/.ssh/github_aspsport`) & DB (`pg_dump venue_system`).
- QRIS **belum** settle otomatis (BRIAPI). Jangan andalkan QRIS untuk transaksi final sampai itu beres.
