"""Station Gaming (arena esport) — data master (admin/HO/manager kelola via
portal). Sesi main (start/topup/stop) ada di app/pos/routes.py (dioperasikan
kasir lewat POS). Prefix: /api/stations"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import User, Venue
from ..security import ROLE_ADMIN_UNIT, ROLE_MANAGER, require_perm
from .models import TIERS, GameSession, GameStation

stations_bp = Blueprint("stations", __name__)

MANAGE = require_perm("station.manage")


def _err(msg, code="bad_request", status=400):
    return jsonify(error=code, message=msg), status


def _current_user():
    return db.session.get(User, int(get_jwt_identity()))


def _scope_vids(u):
    """Venue yg boleh dikelola user. None = semua (admin/head_office)."""
    if not u:
        return []
    if u.role == ROLE_MANAGER:
        return [u.venue_id] if u.venue_id else []
    if u.role == ROLE_ADMIN_UNIT:
        return [v.id for v in Venue.query.filter_by(area_id=u.area_id).all()] if u.area_id else []
    return None


def _active_sessions(station_ids):
    if not station_ids:
        return {}
    rows = GameSession.query.filter(
        GameSession.station_id.in_(station_ids), GameSession.status == "ongoing"
    ).all()
    return {r.station_id: r for r in rows}


@stations_bp.get("")
@jwt_required()
@MANAGE
def stations_list():
    q = GameStation.query
    vid = request.args.get("venue_id", type=int)
    vids = _scope_vids(_current_user())
    if vid:
        if vids is not None and vid not in vids:
            return _err("Venue di luar cakupan Anda", "forbidden", 403)
        q = q.filter_by(venue_id=vid)
    elif vids is not None:
        q = q.filter(GameStation.venue_id.in_(vids)) if vids else q.filter(db.false())
    stations = q.order_by(GameStation.venue_id, GameStation.tier, GameStation.code).all()
    active = _active_sessions([s.id for s in stations])
    return jsonify(count=len(stations), stations=[s.to_dict(active.get(s.id)) for s in stations]), 200


@stations_bp.post("")
@jwt_required()
@MANAGE
def stations_create():
    d = request.get_json(silent=True) or {}
    for f in ("venue_id", "code", "name"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    vids = _scope_vids(_current_user())
    if vids is not None and int(d["venue_id"]) not in vids:
        return _err("Venue di luar cakupan Anda", "forbidden", 403)
    if not db.session.get(Venue, d["venue_id"]):
        return _err("Venue tidak ditemukan", "not_found", 404)
    tier = d.get("tier", "reguler")
    if tier not in TIERS:
        return _err(f"Tier tidak valid ({', '.join(TIERS)})")
    if GameStation.query.filter_by(venue_id=d["venue_id"], code=d["code"]).first():
        return _err("Kode station sudah dipakai di venue ini", "duplicate", 409)
    s = GameStation(
        venue_id=d["venue_id"], code=d["code"], name=d["name"], tier=tier,
        hourly_rate=float(d.get("hourly_rate") or 0), is_active=True,
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(station=s.to_dict()), 201


@stations_bp.put("/<int:sid>")
@jwt_required()
@MANAGE
def stations_update(sid):
    s = db.session.get(GameStation, sid)
    if not s:
        return _err("Station tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and s.venue_id not in vids:
        return _err("Station di luar cakupan Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    if "code" in d and d["code"] and d["code"] != s.code:
        if GameStation.query.filter_by(venue_id=s.venue_id, code=d["code"]).first():
            return _err("Kode station sudah dipakai di venue ini", "duplicate", 409)
        s.code = d["code"]
    if "name" in d and d["name"]:
        s.name = d["name"]
    if "tier" in d:
        if d["tier"] not in TIERS:
            return _err(f"Tier tidak valid ({', '.join(TIERS)})")
        s.tier = d["tier"]
    if "hourly_rate" in d:
        s.hourly_rate = float(d["hourly_rate"] or 0)
    if "is_active" in d:
        s.is_active = bool(d["is_active"])
    db.session.commit()
    active = _active_sessions([s.id])
    return jsonify(station=s.to_dict(active.get(s.id))), 200


@stations_bp.delete("/<int:sid>")
@jwt_required()
@MANAGE
def stations_delete(sid):
    s = db.session.get(GameStation, sid)
    if not s:
        return _err("Station tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and s.venue_id not in vids:
        return _err("Station di luar cakupan Anda", "forbidden", 403)
    if GameSession.query.filter_by(station_id=sid, status="ongoing").first():
        return _err("Station sedang dipakai (ada sesi berjalan) — stop dulu sesinya", "in_use", 409)
    if GameSession.query.filter_by(station_id=sid).first():
        return _err(
            "Station punya riwayat sesi — nonaktifkan saja (jangan hapus) agar riwayat tak hilang.",
            "has_dependencies", 409,
        )
    db.session.delete(s)
    db.session.commit()
    return jsonify(message="Station dihapus"), 200
