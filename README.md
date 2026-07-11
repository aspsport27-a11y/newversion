# ASP Sport System — Venue Management System

Sistem manajemen terintegrasi untuk bisnis multi-venue olahraga (13 unit: lapangan bola, mini soccer, waterpark, futsal, padel, esport). 4 role, 7 modul.

**Live:** https://portal.aspsports.id

## Tech Stack
- **Backend:** Python Flask + SQLAlchemy + JWT (PostgreSQL)
- **Frontend:** Vue 3 + Vite + Pinia + Vue Router + Tailwind + Chart.js
- **Infra:** Nginx (reverse proxy + SSL Let's Encrypt), Gunicorn, systemd

## Struktur Repo
```
backend/    # Flask REST API (app factory, models, auth) — lihat backend/README.md
frontend/   # Vue 3 SPA (login, dashboard, venue)
database/   # schema.sql (17 tabel PostgreSQL)
docs/       # desain teknis, ringkasan project, quick start
```

## Setup Singkat

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # isi kredensial
psql -d venue_system -f ../database/schema.sql   # sekali saja
flask create-admin --username admin --email admin@aspsports.id --password '<pw>' --role admin
gunicorn --bind 127.0.0.1:8000 wsgi:app
```

### Frontend
```bash
cd frontend
npm install
npm run dev       # dev (proxy /api ke :8000)
npm run build     # produksi → dist/
```

## Status
- ✅ **Fase 1** — Autentikasi (JWT, role-based) + Models (17 tabel) + Dashboard/Venue UI
- ⏳ **Fase 2** — Sales module (bookings, payment, daily sales)
- ⏳ Fase 3–7 — Operational, Payroll, Procurement, Reports, Testing/Launch

Lihat `docs/PROJECT_SUMMARY.md` untuk rincian lengkap.

## Roles
`admin` · `head_office` · `manager_unit` · `staff` (kasir)
