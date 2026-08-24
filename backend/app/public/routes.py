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
    CoachAvailability,
    CoachAvailabilityException,
    Facility,
    FacilityBooking,
    Order,
    OrderItem,
    coach_available_ranges,
    coach_declared_available,
    day_type_for_date,
    facility_rate_for_hour,
    ranges_cover,
)

public_bp = Blueprint("public", __name__)

RATE = "30 per minute"


def _err(msg, code="bad_request", status=400):
    return jsonify(error=code, message=msg), status


def _t_mins_pub(t, as_end=False):
    """Jam → menit; 00:00 sbg akhir rentang = jam ke-24 (konvensi yg sama dgn
    jam tutup lapangan — lihat HANDOVER §9)."""
    m = t.hour * 60 + t.minute
    return 24 * 60 if (as_end and m == 0) else m


@public_bp.get("/board")
@limiter.limit(RATE)
def public_board():
    """Papan jadwal layar venue (TV). Token-gated (venues.display_token) — SATU
    PENGECUALIAN lain dari aturan anonim: menampilkan NAMA DEPAN customer, tapi
    hanya bagi pemegang token rahasia venue (buat layar internal di venue).
    Kembalikan lapangan aktif + booking hari ini (nama depan + jam)."""
    token = (request.args.get("token") or "").strip()
    if not token:
        return _err("token wajib")
    venue = Venue.query.filter_by(display_token=token).first()
    if not venue:
        return _err("Token tidak valid", "not_found", 404)

    # "hari ini" waktu lokal WITA (UTC+8) — konsisten dgn modul absensi
    today = (datetime.utcnow() + timedelta(hours=8)).date()
    d_arg = request.args.get("date")
    if d_arg:
        try:
            today = date.fromisoformat(d_arg)
        except ValueError:
            pass

    facs = (
        Facility.query.filter_by(venue_id=venue.id, is_active=True)
        .order_by(Facility.name).all()
    )
    courts = [{
        "id": f.id, "name": f.name,
        "open": f.open_time.strftime("%H:%M") if f.open_time else None,
        "close": f.close_time.strftime("%H:%M") if f.close_time else None,
    } for f in facs]

    rows = (
        db.session.query(FacilityBooking, Order.customer_name)
        .outerjoin(OrderItem, FacilityBooking.order_item_id == OrderItem.id)
        .outerjoin(Order, OrderItem.order_id == Order.id)
        .filter(
            FacilityBooking.venue_id == venue.id,
            FacilityBooking.booking_date == today,
            FacilityBooking.status != "cancelled",
        ).all()
    )
    bookings = []
    for fb, cname in rows:
        name = (cname or "").strip()
        first = name.split(" ")[0] if name else "Booking"  # NAMA DEPAN saja
        bookings.append({
            "court_id": fb.facility_id,
            "start": fb.start_time.strftime("%H:%M"),
            "end": fb.end_time.strftime("%H:%M"),
            "name": first,
            "coaching": fb.coach_id is not None,
        })

    return jsonify(
        venue=venue.name, date=today.isoformat(), courts=courts, bookings=bookings,
    ), 200


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

    # --- coaching: apakah ADA coach yg bisa dipakai di slot ini? ---
    # Sengaja TANPA nama coach (keputusan user): halaman publik cukup memberi
    # tahu "coaching tersedia", penentuan orangnya saat customer menghubungi
    # venue. Rentang & booking coach diambil SEKALI di sini, bukan per slot,
    # supaya endpoint publik tak menembak DB puluhan kali.
    coaches = Coach.query.filter_by(venue_id=fac.venue_id, is_active=True).all()
    coach_ctx = []
    if coaches:
        cids = [c.id for c in coaches]
        busy = {}
        for b in FacilityBooking.query.filter(
            FacilityBooking.coach_id.in_(cids),
            FacilityBooking.booking_date == d,
            FacilityBooking.status == "booked",
        ).all():
            busy.setdefault(b.coach_id, []).append(
                (datetime.combine(d, b.start_time), _end_dt(b.end_time, b.start_time))
            )
        for c in coaches:
            coach_ctx.append((coach_available_ranges(c.id, d), busy.get(c.id, [])))

    def _coach_free(cur, slot_end):
        """Ada coach yg menyatakan bisa DAN belum mengajar di rentang ini."""
        for ranges, taken in coach_ctx:
            if not ranges_cover(ranges, cur.time(), slot_end.time()):
                continue
            if any(bs < slot_end and be > cur for bs, be in taken):
                continue
            return True
        return False

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
                # cuma relevan utk slot yg court-nya masih kosong
                "coach_available": (not is_booked) and _coach_free(cur, slot_end),
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


# ------------------------------------------------------------------
# Ketersediaan coach — diisi SENDIRI oleh coach lewat tautan rahasianya.
# Coach = pihak ke-3 (mitra), sengaja TANPA akun/login supaya nol friksi;
# token yg sama dipakai utk lihat jadwal & mengatur ketersediaan.
# ------------------------------------------------------------------
def _coach_by_token():
    token = (request.args.get("token") or "").strip()
    if not token:
        return None, _err("Token wajib diisi")
    coach = Coach.query.filter_by(schedule_token=token, is_active=True).first()
    if coach is None:
        return None, _err("Tautan tidak berlaku", "not_found", 404)
    return coach, None


def _parse_hm(s):
    try:
        return datetime.strptime(s, "%H:%M").time()
    except (TypeError, ValueError):
        return None


def _conflicting_sessions(coach):
    """Sesi mendatang di luar ketersediaan coach — logikanya dipakai bersama
    dgn portal manajer, jadi tinggal di pos/services (jangan disalin)."""
    from ..pos.services import coach_conflicting_sessions

    return coach_conflicting_sessions(coach.id)


@public_bp.get("/coach-availability")
@limiter.limit("20 per minute")
def coach_availability_get():
    coach, err = _coach_by_token()
    if err:
        return err
    pattern = CoachAvailability.query.filter_by(coach_id=coach.id).order_by(
        CoachAvailability.weekday, CoachAvailability.start_time
    ).all()
    excs = CoachAvailabilityException.query.filter_by(coach_id=coach.id).filter(
        CoachAvailabilityException.date >= date.today()
    ).order_by(CoachAvailabilityException.date).all()
    return jsonify(
        coach={"name": coach.name},
        pattern=[p.to_dict() for p in pattern],
        exceptions=[e.to_dict() for e in excs],
        conflicts=_conflicting_sessions(coach),
        updated_at=coach.availability_updated_at.isoformat() if coach.availability_updated_at else None,
    ), 200


@public_bp.put("/coach-availability")
@limiter.limit("20 per minute")
def coach_availability_set():
    """Simpan ULANG seluruh pola mingguan (ganti total, bukan tambah)."""
    coach, err = _coach_by_token()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    rows = d.get("pattern")
    if not isinstance(rows, list):
        return _err("Format pola tidak valid")
    if len(rows) > 50:
        return _err("Terlalu banyak rentang jam")

    parsed = []
    for r in rows:
        try:
            wd = int(r.get("weekday"))
        except (TypeError, ValueError):
            return _err("Hari tidak valid")
        if wd < 0 or wd > 6:
            return _err("Hari tidak valid")
        st, en = _parse_hm(r.get("start_time")), _parse_hm(r.get("end_time"))
        if st is None or en is None:
            return _err("Jam tidak valid")
        # 00:00 sbg jam SELESAI = tengah malam (akhir hari), bukan awal hari
        if _t_mins_pub(en, as_end=True) <= _t_mins_pub(st):
            return _err("Jam selesai harus setelah jam mulai")
        parsed.append((wd, st, en))

    CoachAvailability.query.filter_by(coach_id=coach.id).delete()
    for wd, st, en in parsed:
        db.session.add(CoachAvailability(coach_id=coach.id, weekday=wd, start_time=st, end_time=en))
    coach.availability_updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(
        pattern=[p.to_dict() for p in CoachAvailability.query.filter_by(coach_id=coach.id)
                 .order_by(CoachAvailability.weekday, CoachAvailability.start_time).all()],
        conflicts=_conflicting_sessions(coach),
    ), 200


@public_bp.post("/coach-availability/exception")
@limiter.limit("20 per minute")
def coach_availability_exception_add():
    coach, err = _coach_by_token()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    try:
        dt = date.fromisoformat(d.get("date"))
    except (TypeError, ValueError):
        return _err("Tanggal tidak valid")
    if dt < date.today():
        return _err("Tanggal sudah lewat")
    available = bool(d.get("available"))
    st = en = None
    if available:
        st, en = _parse_hm(d.get("start_time")), _parse_hm(d.get("end_time"))
        if st is None or en is None:
            return _err("Isi jam mulai & selesai")
        if _t_mins_pub(en, as_end=True) <= _t_mins_pub(st):
            return _err("Jam selesai harus setelah jam mulai")
    else:
        # libur seharian menggantikan pengecualian lain di tanggal itu
        CoachAvailabilityException.query.filter_by(coach_id=coach.id, date=dt).delete()
    db.session.add(CoachAvailabilityException(
        coach_id=coach.id, date=dt, available=available,
        start_time=st, end_time=en, note=(d.get("note") or None),
    ))
    coach.availability_updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(
        exceptions=[e.to_dict() for e in CoachAvailabilityException.query
                    .filter_by(coach_id=coach.id)
                    .filter(CoachAvailabilityException.date >= date.today())
                    .order_by(CoachAvailabilityException.date).all()],
        conflicts=_conflicting_sessions(coach),
    ), 200


@public_bp.delete("/coach-availability/exception/<int:eid>")
@limiter.limit("20 per minute")
def coach_availability_exception_del(eid):
    coach, err = _coach_by_token()
    if err:
        return err
    e = db.session.get(CoachAvailabilityException, eid)
    if e is None or e.coach_id != coach.id:
        return _err("Data tidak ditemukan", "not_found", 404)
    db.session.delete(e)
    coach.availability_updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(message="Dihapus"), 200
