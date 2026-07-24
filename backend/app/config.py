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

    # --- BRIAPI QRIS (standar SNAP BI) ---
    # Kalau kredensial kosong → integrasi mati & QRIS balik ke perilaku lama
    # (payment 'pending', dikonfirmasi manual). Aman dinyalakan bertahap.
    # Sandbox: https://sandbox.partner.api.bri.co.id | Prod: https://partner.api.bri.co.id
    BRI_BASE_URL = os.environ.get("BRI_BASE_URL", "https://sandbox.partner.api.bri.co.id")
    BRI_CLIENT_ID = os.environ.get("BRI_CLIENT_ID", "")          # consumer key → X-CLIENT-KEY
    BRI_CLIENT_SECRET = os.environ.get("BRI_CLIENT_SECRET", "")  # utk tanda tangan simetris
    BRI_PARTNER_ID = os.environ.get("BRI_PARTNER_ID", "")        # X-PARTNER-ID
    BRI_CHANNEL_ID = os.environ.get("BRI_CHANNEL_ID", "")        # CHANNEL-ID
    # File private key RSA (PKCS#8 PEM) utk tanda tangan asimetris saat ambil access token
    BRI_PRIVATE_KEY_PATH = os.environ.get("BRI_PRIVATE_KEY_PATH", "")
    # Public key RSA milik BRI — utk memverifikasi tanda tangan notifikasi (webhook).
    # Tanpa ini webhook SELALU ditolak (aman: lebih baik tolak drpd salah kredit).
    BRI_PUBLIC_KEY_PATH = os.environ.get("BRI_PUBLIC_KEY_PATH", "")
    # Identitas merchant QRIS
    BRI_MERCHANT_ID = os.environ.get("BRI_MERCHANT_ID", "")
    BRI_TERMINAL_ID = os.environ.get("BRI_TERMINAL_ID", "")
    # Masa berlaku QR (detik); lewat ini QR dianggap kedaluwarsa
    BRI_QR_TTL_SECONDS = int(os.environ.get("BRI_QR_TTL_SECONDS", "900"))
    BRI_TIMEOUT = int(os.environ.get("BRI_TIMEOUT", "15"))  # timeout HTTP ke BRI
