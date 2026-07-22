"""Instansiasi ekstensi Flask (dipakai lintas modul untuk menghindari circular import)."""
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
# dipakai endpoint publik (jadwal.aspsports.id) — tanpa login, jadi perlu
# batasi laju per-IP supaya tak gampang di-scrape/disalahgunakan
limiter = Limiter(key_func=get_remote_address, default_limits=[])
