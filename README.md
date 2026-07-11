# ASP Sport System — Venue Management System

Sistem manajemen terintegrasi untuk bisnis multi-venue olahraga (13 unit: lapangan bola, mini soccer, waterpark, futsal, padel, esport). 4 role, 7 modul. Termasuk **POS kasir** dengan shift & rekonsiliasi kas.

**Live:** admin → https://portal.aspsports.id · POS → https://pos.aspsports.id

## Tech Stack
- **Backend:** Python Flask + SQLAlchemy + JWT (PostgreSQL) — satu API dipakai semua frontend
- **Frontend:** Vue 3 + Vite + Pinia + Vue Router + Tailwind (+ Chart.js di admin)
- **Infra:** Nginx (reverse proxy + SSL Let's Encrypt), Gunicorn, systemd

## Struktur Repo
```
backend/         # Flask REST API — auth, models, modul POS (app/pos/)
frontend-admin/  # Vue SPA admin  → portal.aspsports.id
frontend-pos/    # Vue SPA POS    → pos.aspsports.id
database/        # schema.sql + migrations/
docs/            # desain teknis, ringkasan, quick start
```

## Arsitektur
Satu backend + banyak frontend. Mesin transaksi generik: `orders` + `order_items`
(item = produk / tiket / sewa / booking). Pembayaran cash + QRIS (provider colok-lepas;
QRIS via BRIAPI MPM Dinamis + Notifikasi, menyusul). Rekonsiliasi kas per-shift.

## Setup

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # isi kredensial
psql -d venue_system -f ../database/schema.sql
psql -d venue_system -f ../database/migrations/002_pos_m0.sql
flask create-admin --username admin --email admin@aspsports.id --password '<pw>' --role admin
gunicorn --bind 127.0.0.1:8000 wsgi:app
```

### Frontend (admin / pos)
```bash
cd frontend-admin   # atau frontend-pos
npm install
npm run dev         # dev (proxy /api ke :8000)
npm run build       # produksi → dist/
```

## Status pengembangan
- ✅ **Fase 1** — Auth (JWT, role) + Models (17 tabel) + admin (dashboard, venue)
- ✅ **M0** — Fondasi data POS (11 tabel: orders, order_items, payments, shifts, products, dll)
- ✅ **M1** — POS MVP: login PIN, shift + rekonsiliasi kas, jual produk, cash lunas + potong stok, struk. QRIS stub (BRIAPI menyusul).
- ⏳ **M2** — Booking lapangan (jadwal + ketersediaan)
- ⏳ **M3** — Integrasi BRIAPI QRIS, admin produk/laporan
- ⏳ **M4** — Rollout multi-venue + polish

## Roles
`admin` · `head_office` · `manager_unit` · `staff` (kasir)

## POS — endpoint utama (`/api/pos`)
`auth/login` (PIN+terminal) · `me` · `products` · `shifts/{open,current,close,cash-movement}` · `orders` (create/get/pay)
