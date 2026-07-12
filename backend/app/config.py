"""Konfigurasi aplikasi — dibaca dari environment (.env)."""
import os
from datetime import timedelta

from dotenv import load_dotenv

# muat .env dari root project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    # --- Database ---
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # --- Flask ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")

    # --- JWT ---
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.environ.get("JWT_ACCESS_HOURS", "8"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.environ.get("JWT_REFRESH_DAYS", "30"))
    )

    # --- CORS ---
    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS", "https://portal.aspsports.id"
    ).split(",")

    # --- Upload lampiran (bukti operasional) ---
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/opt/aspsport-uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB per upload
