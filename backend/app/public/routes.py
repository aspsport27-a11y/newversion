"""Endpoint publik (tanpa login) utk halaman jadwal.aspsports.id.

Endpoint jadwal umum cuma expose ketersediaan slot (available/booked) —
TIDAK PERNAH kirim customer_name/phone/email, harga transaksi, atau data staf.
Dibatasi rate-limit per-IP krn tanpa auth. Prefix: /api/public

PENGECUALIAN SATU-SATUNYA: `/coach-schedule` memang mengirim nama & no HP
customer, tapi HANYA kalau pemanggil memegang token rahasia coach (keputusan
user: coach perlu bisa menghubungi muridnya langsung). Karena itu endpoint
tsb dijaga khusus — lihat komentar di sana.
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from ..extensions import db, limiter
from ..models import Area, Venue
from ..pos.models import (
    Coach,
    Facility,
    FacilityBooking,
    Order,
    OrderItem,
    day_type_for_date,
    facility_rate_for_hour,
)

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
            "hourly_rate": float(f.hourly_rate or 0),  # tarif dasar — bisa beda per jam, lihat rate_rules
            "open_time": hm(f.open_time),
            "close_time": hm(f.close_time),
            "slot_minutes": f.slot_minutes or 60,
            "rate_rules": [
                {
                    "label": r.label, "start_time": hm(r.start_time),
                    "end_time": hm(r.end_time), "hourly_rate": float(r.hourly_rate or 0),
                }
                for r in f.rate_rules
            ],
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

    # jam tutup yang lewat tengah malam (00:00, atau <= jam mulai spt buka 06:00
    # tutup 03:00) mesti dianggap HARI BERIKUTNYA — kalau tidak, tutup dibaca
    # "lebih kecil" dari buka & tak ada slot yang ter-generate sama sekali.
    def _end_dt(t, start=None):
        dt = datetime.combine(d, t)
        if t == datetime.min.time() or (start is not None and t <= start):
            dt += timedelta(days=1)
        return dt

    # flag ke-3 = slot ini sesi coaching (ada coach). Hanya BOOLEAN — nama
    # customer maupun nama coach TIDAK pernah dikirim ke halaman publik.
    booked_ranges = [
        (datetime.combine(d, b.start_time), _end_dt(b.end_time, b.start_time), bool(b.coach_id))
        for b in booked
    ]

    slots = []
    dtype = day_type_for_date(d)  # tarif ikut kategori hari tanggal ini
    cur = datetime.combine(d, fac.open_time)
    end_of_day = _end_dt(fac.close_time, fac.open_time)
    while cur < end_of_day:
        slot_end = cur + timedelta(minutes=slot_minutes)
        overlap = [r for r in booked_ranges if r[0] < slot_end and r[1] > cur]
        is_booked = bool(overlap)
        slots.append(
            {
                "start_time": cur.strftime("%H:%M"),
                "end_time": slot_end.strftime("%H:%M"),
                "status": "booked" if is_booked else "available",
                "coaching": any(r[2] for r in overlap),
                "rate": facility_rate_for_hour(fac, cur.hour, dtype),
            }
        )
        cur = slot_end

    return jsonify(facility_id=fid, date=d.isoformat(), slots=slots), 200


@public_bp.get("/coach-schedule")
@limiter.limit("10 per minute")
def public_coach_schedule():
    """Jadwal pribadi coach — dibuka dgn TOKEN RAHASIA, tanpa login.

    Ini satu-satunya endpoint publik yg mengirim data pribadi customer (nama
    & no HP), atas keputusan user supaya coach bisa menghubungi muridnya.
    Pengamanannya berlapis:
      - kunci = token acak 24 byte (secrets), BUKAN id yg bisa di-enumerasi;
      - rate limit lebih ketat dr endpoint publik lain (10/menit) — bikin
        tebak-tebakan token tak praktis;
      - hanya sesi YANG AKAN DATANG (hari ini s.d. 60 hari) — riwayat lama
        tak pernah ikut terekspos;
      - token bisa di-reset dr portal kalau bocor (token lama langsung mati).
    Coach nonaktif → 404 (aksesnya otomatis putus).
    """
    token = (request.args.get("token") or "").strip()
    if not token:
        return _err("Token wajib diisi")
    coach = Coach.query.filter_by(schedule_token=token, is_active=True).first()
    if coach is None:
        return _err("Tautan tidak berlaku", "not_found", 404)

    today = date.today()
    until = today + timedelta(days=60)
    rows = (
        db.session.query(FacilityBooking, Facility, OrderItem, Order)
        .join(Facility, FacilityBooking.facility_id == Facility.id)
        .outerjoin(OrderItem, FacilityBooking.coaching_item_id == OrderItem.id)
        .outerjoin(Order, OrderItem.order_id == Order.id)
        .filter(
            FacilityBooking.coach_id == coach.id,
            FacilityBooking.status == "booked",
            FacilityBooking.booking_date.between(today, until),
        )
        .order_by(FacilityBooking.booking_date, FacilityBooking.start_time)
        .all()
    )
    venue = db.session.get(Venue, coach.venue_id)
    hm = lambda t: t.strftime("%H:%M") if t else None
    sessions = []
    for fb, fac, item, order in rows:
        if order is not None and order.status == "void":
            continue  # sesi dibatalkan jangan tampil di jadwal coach
        sessions.append({
            "date": fb.booking_date.isoformat(),
            "start_time": hm(fb.start_time),
            "end_time": hm(fb.end_time),
            "facility_name": fac.name,
            "persons": fb.coaching_persons,
            "hours": float(item.quantity) if item is not None else None,
            "customer_name": order.customer_name if order is not None else None,
            "customer_phone": order.customer_phone if order is not None else None,
        })
    return jsonify(
        coach={"name": coach.name},
        venue={"name": venue.name if venue else None, "address": venue.address if venue else None},
        count=len(sessions),
        sessions=sessions,
    ), 200
