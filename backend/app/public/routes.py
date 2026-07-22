"""Endpoint publik (tanpa login) utk halaman jadwal.aspsports.id.

Cuma expose ketersediaan slot (available/booked) — TIDAK PERNAH kirim
customer_name/phone/email, harga transaksi, atau data staf. Dibatasi
rate-limit per-IP krn tanpa auth. Prefix: /api/public
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from ..extensions import db, limiter
from ..models import Area, Venue
from ..pos.models import Facility, FacilityBooking

public_bp = Blueprint("public", __name__)

RATE = "30 per minute"


def _err(msg, code="bad_request", status=400):
    return jsonify(error=code, message=msg), status


@public_bp.get("/venues")
@limiter.limit(RATE)
def public_venues():
    """Venue yg punya minimal 1 facility aktif (yg bisa di-booking per jam)."""
    rows = (
        db.session.query(Venue, Area.name)
        .join(Facility, Facility.venue_id == Venue.id)
        .outerjoin(Area, Venue.area_id == Area.id)
        .filter(Facility.is_active.is_(True), Venue.active.is_(True))
        .distinct()
        .order_by(Venue.name)
        .all()
    )
    venues = [
        {
            "id": v.id,
            "name": v.name,
            "type": v.type,
            "area": area_name,
            "address": v.address,
            "phone": v.phone,
        }
        for v, area_name in rows
    ]
    return jsonify(count=len(venues), venues=venues), 200


@public_bp.get("/facilities")
@limiter.limit(RATE)
def public_facilities():
    vid = request.args.get("venue_id", type=int)
    if not vid:
        return _err("venue_id wajib diisi")
    hm = lambda t: t.strftime("%H:%M") if t else None
    rows = (
        Facility.query.filter_by(venue_id=vid, is_active=True)
        .order_by(Facility.name)
        .all()
    )
    facilities = [
        {
            "id": f.id,
            "name": f.name,
            "type": f.type,
            "hourly_rate": float(f.hourly_rate or 0),
            "open_time": hm(f.open_time),
            "close_time": hm(f.close_time),
            "slot_minutes": f.slot_minutes or 60,
        }
        for f in rows
    ]
    return jsonify(count=len(facilities), facilities=facilities), 200


@public_bp.get("/schedule")
@limiter.limit(RATE)
def public_schedule():
    fid = request.args.get("facility_id", type=int)
    if not fid:
        return _err("facility_id wajib diisi")
    d_str = request.args.get("date") or date.today().isoformat()
    try:
        d = date.fromisoformat(d_str)
    except ValueError:
        return _err("Format tanggal salah (YYYY-MM-DD)")

    max_date = date.today() + timedelta(days=30)
    if d < date.today() or d > max_date:
        return _err("Tanggal di luar rentang yg diizinkan (hari ini s.d. 30 hari ke depan)")

    fac = db.session.get(Facility, fid)
    if not fac or not fac.is_active:
        return _err("Facility tidak ditemukan", "not_found", 404)
    if not fac.open_time or not fac.close_time:
        return jsonify(facility_id=fid, date=d.isoformat(), slots=[]), 200

    slot_minutes = fac.slot_minutes or 60
    booked = FacilityBooking.query.filter(
        FacilityBooking.facility_id == fid,
        FacilityBooking.booking_date == d,
        FacilityBooking.status != "cancelled",
    ).all()

    # jam tutup "00:00" = tengah malam (akhir hari), bukan awal hari — mesti
    # dianggap hari berikutnya spy tak dibaca "lebih kecil" dari jam buka
    def _end_dt(t):
        dt = datetime.combine(d, t)
        if t == datetime.min.time():
            dt += timedelta(days=1)
        return dt

    booked_ranges = [(datetime.combine(d, b.start_time), _end_dt(b.end_time)) for b in booked]

    slots = []
    cur = datetime.combine(d, fac.open_time)
    end_of_day = _end_dt(fac.close_time)
    while cur < end_of_day:
        slot_end = cur + timedelta(minutes=slot_minutes)
        is_booked = any(bs < slot_end and be > cur for bs, be in booked_ranges)
        slots.append(
            {
                "start_time": cur.strftime("%H:%M"),
                "end_time": slot_end.strftime("%H:%M"),
                "status": "booked" if is_booked else "available",
            }
        )
        cur = slot_end

    return jsonify(facility_id=fid, date=d.isoformat(), slots=slots), 200
