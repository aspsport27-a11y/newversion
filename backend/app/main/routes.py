"""Endpoint umum: health check + contoh data (venues) untuk verifikasi ORM."""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import text

from ..extensions import db
from ..models import Venue

main_bp = Blueprint("main", __name__)


@main_bp.get("/health")
def health():
    """Cek liveness + koneksi database."""
    db_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    status = "ok" if db_ok else "degraded"
    return jsonify(status=status, database="up" if db_ok else "down"), (
        200 if db_ok else 503
    )


@main_bp.get("/venues")
@jwt_required()
def list_venues():
    """Daftar venue — membuktikan model tersambung ke tabel nyata."""
    venues = Venue.query.order_by(Venue.code).all()
    return jsonify(count=len(venues), venues=[v.to_dict() for v in venues]), 200
