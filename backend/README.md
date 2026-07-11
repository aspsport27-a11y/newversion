# ASP Sport / Venue Management System — Backend

Backend REST API (Flask + PostgreSQL). **Fase 1: Autentikasi + Models.**

## Stack
- Flask 3 + Flask-SQLAlchemy + Flask-JWT-Extended
- PostgreSQL 16 (database `venue_system`, 17 tabel)
- Gunicorn (systemd service) di belakang Nginx reverse proxy
- Auth: JWT (bcrypt password hashing), role-based (`admin`, `head_office`, `manager_unit`, `staff`)

## Struktur
```
app/
├── __init__.py     # application factory, JWT handlers, error handlers, CLI
├── config.py       # konfigurasi dari .env
├── extensions.py   # db, jwt, migrate, cors
├── security.py     # hashing bcrypt + decorator roles_required
├── models.py       # 17 model memetakan tabel database_schema.sql
├── auth/routes.py  # /api/auth/*
└── main/routes.py  # /api/health, /api/venues
```

## Endpoint (Fase 1)
| Method | Path | Auth | Keterangan |
|--------|------|------|-----------|
| GET  | `/api/health` | - | Liveness + cek DB |
| POST | `/api/auth/login` | - | Login (username/email + password) → access+refresh token |
| POST | `/api/auth/refresh` | refresh token | Perbarui access token |
| GET  | `/api/auth/me` | access token | Profil user saat ini |
| POST | `/api/auth/logout` | access token | Cabut token (blocklist) |
| POST | `/api/auth/reset-password` | access token | Ganti password (butuh password lama) |
| GET  | `/api/venues` | access token | Daftar venue (contoh data) |

## Operasional
```bash
# status / log
systemctl status aspsport-backend
journalctl -u aspsport-backend -f

# restart setelah update kode
systemctl restart aspsport-backend

# buat user baru
sudo -u aspsport /opt/aspsport-backend/venv/bin/flask --app wsgi create-admin \
    --username <u> --email <e> --password <p> --role <admin|head_office|manager_unit|staff>
```

Konfigurasi rahasia ada di `.env` (permission 600). Kredensial DB juga di `/root/venue_system.db.env`.

## Berikutnya (Fase 2+)
Sales module (bookings, payment, daily sales), lalu operational, payroll, procurement, reports — sesuai `PROJECT_SUMMARY.md`.
