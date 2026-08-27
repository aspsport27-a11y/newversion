"""Endpoint POS — Fase M1. Prefix: /api/pos"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import func

from ..extensions import db
from ..models import Employee, User, Venue
from ..perms import has_perm
from ..security import verify_password
from ..stations.models import GameStation
from . import briapi
from .models import Attendance, Coach, CoachingRate, Event, Facility, FacilityBooking, Order, OrderItem, Payment, PosTerminal, Product, ProductCategory, Shift, coach_declared_available, coaching_price_per_hour, day_type_for_date, facility_booking_price
from .services import (
    PosError,
    add_cash_movement,
    add_items_to_order,
    cancel_order,
    close_shift,
    confirm_qris_payment,
    create_order,
    expire_stale_qris,
    generate_order_number,
    is_coach_available,
    open_shift,
    pay_order,
    reschedule_booking,
    sync_qris_payment,
)

log = logging.getLogger(__name__)

pos_bp = Blueprint("pos", __name__)


@pos_bp.errorhandler(PosError)
def _handle_pos_error(e: PosError):
    return jsonify(error=e.code, message=e.message), e.status


def _claims():
    return get_jwt()


def _current_terminal() -> PosTerminal:
    tid = _claims().get("terminal_id")
    terminal = db.session.get(PosTerminal, tid) if tid else None
    if terminal is None:
        raise PosError("Terminal tidak valid pada token", "no_terminal", 401)
    return terminal


def _current_open_shift(terminal_id: int) -> Shift:
    shift = Shift.query.filter_by(terminal_id=terminal_id, status="open").first()
    if shift is None:
        raise PosError("Belum ada shift terbuka. Buka shift dulu.", "no_open_shift", 409)
    return shift


def _D(v, default=0):
    try:
        if v in (None, ""):
            return Decimal(str(default))
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(default))


# ------------------------------------------------------------------
# Auth POS — login PIN + terminal
# ------------------------------------------------------------------
@pos_bp.post("/auth/login")
def pos_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    pin = data.get("pin") or ""
    terminal_code = (data.get("terminal_code") or "").strip()

    if not username or not pin or not terminal_code:
        return jsonify(error="bad_request", message="username, pin, terminal_code wajib"), 400

    terminal = PosTerminal.query.filter_by(code=terminal_code, is_active=True).first()
    if terminal is None:
        return jsonify(error="terminal_not_found", message="Terminal tidak ditemukan/nonaktif"), 404

    user = User.query.filter_by(username=username, active=True).first()
    if user is None or not user.pin_hash or not verify_password(pin, user.pin_hash):
        return jsonify(error="unauthorized", message="Username atau PIN salah"), 401
    if user.role not in ("staff", "manager_unit"):
        return jsonify(
            error="forbidden",
            message="Akun ini tidak diizinkan login ke POS. Gunakan menu Absen untuk absensi.",
        ), 403

    # kalau kasir dibatasi venue, harus cocok dengan venue terminal
    if user.venue_id and user.venue_id != terminal.venue_id:
        return jsonify(error="forbidden", message="Kasir tidak berhak di venue terminal ini"), 403

    user.touch_login()
    db.session.commit()

    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "role": user.role,
            "username": user.username,
            "scope": "pos",
            "terminal_id": terminal.id,
            "venue_id": terminal.venue_id,
        },
    )
    return jsonify(
        access_token=token,
        cashier={"id": user.id, "username": user.username, "role": user.role},
        terminal=terminal.to_dict(),
    ), 200


# ------------------------------------------------------------------
# Absensi — tap PIN di terminal, tanpa login penuh (rekap kehadiran)
# ------------------------------------------------------------------
def _reverse_geocode(location):
    """'lat,lon' -> alamat (termasuk kelurahan kalau ada di data OSM) via
    Nominatim. Gratis, tanpa API key — tapi best-effort: None kalau
    gagal/timeout, absen tetap tercatat tanpa alamat."""
    if not location or "," not in location:
        return None
    try:
        import httpx

        lat, lon = location.split(",", 1)
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "format": "jsonv2", "lat": lat.strip(), "lon": lon.strip(),
                "addressdetails": 1, "accept-language": "id",
            },
            headers={"User-Agent": "ASPSportSystem/1.0 (attendance-geocoding)"},
            timeout=4.0,
        )
        if resp.status_code != 200:
            return None
        addr = resp.json().get("display_name")
        return addr[:255] if addr else None
    except Exception:  # noqa: BLE001 — reverse geocoding tak boleh gagalkan absen
        return None


def _save_absen_photo(data_url, prefix):
    """Simpan foto base64 (data URL) ke UPLOAD_FOLDER/attendance. Return filename / None."""
    import base64
    import os
    import uuid

    from flask import current_app
    try:
        if "," in data_url:
            data_url = data_url.split(",", 1)[1]
        raw = base64.b64decode(data_url)
        if not raw or len(raw) > 2_000_000:  # guard 2MB
            return None
        d = os.path.join(current_app.config["UPLOAD_FOLDER"], "attendance")
        os.makedirs(d, exist_ok=True)
        fn = f"{prefix}_{uuid.uuid4().hex[:8]}.jpg"
        with open(os.path.join(d, fn), "wb") as f:
            f.write(raw)
        return fn
    except Exception:  # noqa: BLE001
        return None


def _save_payment_proof(data_url):
    """Simpan bukti transfer (screenshot/foto) base64 ke UPLOAD_FOLDER/payment_proof."""
    import base64
    import os
    import uuid

    from flask import current_app
    try:
        if "," in data_url:
            data_url = data_url.split(",", 1)[1]
        raw = base64.b64decode(data_url)
        if not raw or len(raw) > 3_000_000:  # guard 3MB
            return None
        d = os.path.join(current_app.config["UPLOAD_FOLDER"], "payment_proof")
        os.makedirs(d, exist_ok=True)
        fn = f"proof_{uuid.uuid4().hex[:8]}.jpg"
        with open(os.path.join(d, fn), "wb") as f:
            f.write(raw)
        return fn
    except Exception:  # noqa: BLE001
        return None


@pos_bp.post("/attendance")
def pos_attendance():
    from datetime import timedelta, timezone

    # venue di Kalimantan Selatan → WITA (UTC+8); simpan waktu lokal (naive)
    now = (datetime.utcnow() + timedelta(hours=8))

    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin") or "")
    terminal_code = (data.get("terminal_code") or "").strip()
    action = (data.get("action") or "in").strip()  # in | out
    if not pin or not terminal_code:
        return jsonify(error="bad_request", message="PIN & terminal wajib"), 400
    if action not in ("in", "out"):
        return jsonify(error="bad_request", message="action harus in/out"), 400

    terminal = PosTerminal.query.filter_by(code=terminal_code, is_active=True).first()
    if terminal is None:
        return jsonify(error="terminal_not_found", message="Terminal tidak ditemukan"), 404

    # cocokkan PIN ke staff di venue terminal (atau tanpa venue)
    candidates = User.query.filter(
        User.pin_hash.isnot(None), User.active.is_(True),
        (User.venue_id == terminal.venue_id) | (User.venue_id.is_(None)),
    ).all()
    matched = [u for u in candidates if verify_password(pin, u.pin_hash)]
    if not matched:
        return jsonify(error="unauthorized", message="PIN tidak dikenal"), 401
    if len(matched) > 1:
        return jsonify(error="ambiguous", message="PIN dipakai >1 orang — hubungi admin"), 409
    user = matched[0]

    name = user.username
    if user.employee_id:
        emp = db.session.get(Employee, user.employee_id)
        if emp:
            name = emp.name

    today = now.date()

    # lokasi GPS (opsional — "lat,lon" dari geolocation browser), verifikasi
    # absen dilakukan di luar/lokasi venue, bukan bukti wajib
    location = (data.get("location") or "").strip()[:100] or None
    address = _reverse_geocode(location) if location else None

    if action == "in":
        row = Attendance.query.filter_by(user_id=user.id, date=today).first()
        if row is None:
            row = Attendance(
                user_id=user.id, employee_id=user.employee_id,
                venue_id=terminal.venue_id, terminal_id=terminal.id, date=today,
            )
            db.session.add(row)
        if row.check_in:
            return jsonify(error="already", message=f"{name} sudah absen masuk hari ini "
                           f"({row.check_in.strftime('%H:%M')})"), 409
        row.status = None  # ternyata datang → batalkan tanda izin/sakit/cuti kalau ada
        row.check_in = now
        row.check_in_location = location
        row.check_in_address = address
    else:
        # absen pulang → tutup shift TERBUKA (sudah masuk, belum pulang), termasuk
        # shift malam yg masuk kemarin & pulang lewat tengah malam. Cari dlm 18 jam
        # terakhir supaya sisa lupa-checkout hari-hari lama tak ikut ke-tutup.
        row = (
            Attendance.query
            .filter(
                Attendance.user_id == user.id,
                Attendance.check_in.isnot(None),
                Attendance.check_out.is_(None),
                Attendance.check_in >= now - timedelta(hours=18),
            )
            .order_by(Attendance.check_in.desc())
            .first()
        )
        if row is None:
            return jsonify(error="no_checkin", message=f"{name} belum absen masuk "
                           "(atau shift-nya sudah lewat > 18 jam)"), 409
        row.check_out = now
        row.check_out_location = location
        row.check_out_address = address

    # foto bukti (opsional — device tanpa kamera tetap tercatat, ditandai tanpa foto)
    db.session.flush()  # pastikan row.id ada utk nama file
    photo = data.get("photo")
    if photo:
        fn = _save_absen_photo(photo, f"att{row.id}_{action}")
        if fn:
            if action == "in":
                row.check_in_photo = fn
            else:
                row.check_out_photo = fn
    db.session.commit()

    label = "Masuk" if action == "in" else "Pulang"
    has_photo = bool(row.check_in_photo if action == "in" else row.check_out_photo)
    return jsonify(
        ok=True, name=name, action=action,
        time=now.strftime("%H:%M"), photo=has_photo,
        message=f"Absen {label} — {name} ({now.strftime('%H:%M')})"
                + ("" if has_photo else " — tanpa foto"),
    ), 200


@pos_bp.get("/me")
@jwt_required()
def pos_me():
    terminal = _current_terminal()
    shift = Shift.query.filter_by(terminal_id=terminal.id, status="open").first()
    venue = db.session.get(Venue, terminal.venue_id)
    has_facility = (
        db.session.query(Facility.id)
        .filter_by(venue_id=terminal.venue_id, is_active=True)
        .first()
        is not None
    )
    return jsonify(
        cashier_id=int(get_jwt_identity()),
        username=_claims().get("username"),
        terminal=terminal.to_dict(),
        venue={"id": venue.id, "code": venue.code, "name": venue.name, "type": venue.type} if venue else None,
        booking_enabled=has_facility,  # True = mode booking lapangan; False = mode tiketing
        qris_dynamic=briapi.is_configured(),  # True = QR otomatis via BRIAPI; False = QRIS manual (upload bukti)
        open_shift=shift.to_dict() if shift else None,
    ), 200


# ------------------------------------------------------------------
# Produk (katalog venue terminal)
# ------------------------------------------------------------------
@pos_bp.get("/products")
@jwt_required()
def pos_products():
    terminal = _current_terminal()
    from .promos import product_public
    from .services import ticket_unit_price

    products = (
        Product.query.filter_by(venue_id=terminal.venue_id, is_active=True)
        .order_by(Product.name)
        .all()
    )
    cat_names = {c.id: c.name for c in ProductCategory.query.all()}
    out = []
    for p in products:
        d = product_public(p)
        d["category_name"] = cat_names.get(p.category_id)
        if p.is_ticket:
            # harga tiket berlaku hari ini (weekday/weekend/libur otomatis)
            d["effective_price"] = ticket_unit_price(p)
        out.append(d)
    return jsonify(count=len(out), products=out), 200


# ------------------------------------------------------------------
# Laporan penjualan hari ini per kategori (untuk kasir, tanpa detail item)
# ------------------------------------------------------------------
_REPORT_LABELS = {
    "ticket": "Tiket Masuk", "booking": "Booking Lapangan",
    "rental": "Station Gaming", "coaching": "Coaching", "event": "Event",
}


@pos_bp.get("/reports/category-daily")
@jwt_required()
def report_category_daily():
    """Uang masuk hari ini per kategori — berdasar TANGGAL PEMBAYARAN
    (Payment.paid_at), bukan tanggal/status order. Booking yg baru DP hari
    ini utk tanggal main nanti tetap terhitung (uangnya beneran masuk hari
    ini, meski order-nya masih 'partial' bukan 'paid'). Kalau 1 order isinya
    campur & baru dibayar sebagian, jumlah pembayaran dialokasikan
    proporsional ke tiap item sesuai porsi line_total-nya."""
    terminal = _current_terminal()
    today = date.today()

    payments = (
        Payment.query.join(Order, Payment.order_id == Order.id)
        .filter(
            Order.venue_id == terminal.venue_id,
            Payment.status == "paid",
            func.date(Payment.paid_at) == today,
        )
        .all()
    )

    cat_names = {c.id: c.name for c in ProductCategory.query.all()}
    product_cat = dict(db.session.query(Product.id, Product.category_id).all())

    # kategori yg RELEVAN utk venue ini (punya master data-nya) — selalu
    # ditampilkan biar kasir lihat gambaran lengkap, walau blm ada penjualan
    # hari ini (amount 0), bukan cuma yg kebetulan ada transaksi
    prod_cat_ids = {
        cid
        for (cid,) in Product.query.filter_by(
            venue_id=terminal.venue_id, is_active=True, is_ticket=False
        ).with_entities(Product.category_id).distinct()
    }
    # tiap grup simpan rincian item (dict nama→{qty,amount}) utk accordion
    groups = {cat_names.get(cid, "Tanpa Kategori"): {"category": cat_names.get(cid, "Tanpa Kategori"), "qty": 0.0, "amount": 0.0, "items": {}} for cid in prod_cat_ids}
    if Facility.query.filter_by(venue_id=terminal.venue_id, is_active=True).first():
        label = _REPORT_LABELS["booking"]
        groups[label] = {"category": label, "qty": 0.0, "amount": 0.0, "items": {}}
    if Product.query.filter_by(venue_id=terminal.venue_id, is_active=True, is_ticket=True).first():
        label = _REPORT_LABELS["ticket"]
        groups[label] = {"category": label, "qty": 0.0, "amount": 0.0, "items": {}}
    if GameStation.query.filter_by(venue_id=terminal.venue_id, is_active=True).first():
        label = _REPORT_LABELS["rental"]
        groups[label] = {"category": label, "qty": 0.0, "amount": 0.0, "items": {}}
    if Coach.query.filter_by(venue_id=terminal.venue_id, is_active=True).first():
        label = _REPORT_LABELS["coaching"]
        groups[label] = {"category": label, "qty": 0.0, "amount": 0.0, "items": {}}

    # POS kenal 3 metode bayar (cash/qris/transfer) — selalu tampilkan semua
    # walau ada yg 0, biar kasir gampang cocokkan fisik uang di laci
    method_totals = {"cash": 0.0, "qris": 0.0, "transfer": 0.0}

    total = 0.0
    order_ids_seen = set()
    qty_counted = set()  # item.id yg qty-nya sudah dihitung (biar tak dobel per pembayaran)
    for p in payments:
        method_totals[p.method] = method_totals.get(p.method, 0.0) + float(p.amount or 0)

        order = p.order
        # pembagi = jumlah line_total semua item (= subtotal, SEBELUM diskon).
        # JANGAN pakai total_amount (setelah diskon): line_total menjumlah ke
        # subtotal, jadi kalau ada diskon porsinya >100% & uang laporan jadi
        # lebih besar dr yg benar-benar dibayar. Diskon otomatis terbagi rata.
        items_sum = float(sum(float(i.line_total or 0) for i in order.items)) if order else 0
        if not order or items_sum <= 0 or not order.items:
            continue
        order_ids_seen.add(order.id)
        pay_amount = float(p.amount or 0)
        for item in order.items:
            share = float(item.line_total or 0) / items_sum
            if item.item_type == "product":
                label = cat_names.get(product_cat.get(item.product_id), "Tanpa Kategori")
            else:
                label = _REPORT_LABELS.get(item.item_type, item.item_type)
            g = groups.setdefault(label, {"category": label, "qty": 0.0, "amount": 0.0, "items": {}})
            g["amount"] += pay_amount * share
            total += pay_amount * share
            # rincian per nama item (digabung kalau nama sama)
            nm = item.name_snapshot or "—"
            det = g["items"].setdefault(nm, {"name": nm, "qty": 0.0, "amount": 0.0})
            det["amount"] += pay_amount * share
            # qty = jumlah item UTUH, dihitung sekali saja (jangan ikut porsi
            # nilai/pembayaran — itu bikin jumlah item jadi pecahan)
            if item.id not in qty_counted:
                qty_counted.add(item.id)
                q = float(item.quantity or 0)
                g["qty"] += q
                det["qty"] += q

    by_category = sorted(
        [{
            "category": g["category"],
            "qty": round(g["qty"], 2),
            "amount": round(g["amount"], 2),
            "items": sorted(
                [{"name": d["name"], "qty": round(d["qty"], 2), "amount": round(d["amount"], 2)}
                 for d in g["items"].values()],
                key=lambda x: -x["amount"],
            ),
        } for g in groups.values()],
        key=lambda x: -x["amount"],
    )
    by_method = [
        {"method": "cash", "label": "Cash", "amount": round(method_totals.get("cash", 0.0), 2)},
        {"method": "qris", "label": "QRIS", "amount": round(method_totals.get("qris", 0.0), 2)},
        {"method": "transfer", "label": "Transfer Bank", "amount": round(method_totals.get("transfer", 0.0), 2)},
    ]
    return jsonify(
        date=today.isoformat(),
        order_count=len(order_ids_seen),
        total=round(total, 2),
        by_category=by_category,
        by_method=by_method,
    ), 200


# ------------------------------------------------------------------
# Coaching (padel) — tarif + daftar coach & ketersediaannya
# ------------------------------------------------------------------
@pos_bp.get("/coaching")
@jwt_required()
def pos_coaching():
    """Tarif coaching + daftar coach venue ini. Kalau diberi date/start_time/
    end_time, tiap coach ditandai `available` — POS memakainya utk menyaring
    coach yg sudah mengajar di jam itu (termasuk di court lain).

    Venue tanpa coach → coaches kosong; POS otomatis menyembunyikan UI coaching."""
    terminal = _current_terminal()
    rate = db.session.get(CoachingRate, terminal.venue_id)
    coaches = (
        Coach.query.filter_by(venue_id=terminal.venue_id, is_active=True)
        .order_by(Coach.name)
        .all()
    )

    d_str = request.args.get("date")
    s_str = request.args.get("start_time")
    e_str = request.args.get("end_time")
    bdate = start = end = None
    if d_str and s_str and e_str:
        try:
            bdate = date.fromisoformat(d_str)
            start = datetime.strptime(s_str, "%H:%M").time()
            end = datetime.strptime(e_str, "%H:%M").time()
        except (ValueError, TypeError):
            bdate = start = end = None  # abaikan filter kalau formatnya salah

    out = []
    for c in coaches:
        row = c.to_dict()
        # `available` = tak bentrok (belum mengajar) → kalau False, coach memang
        # tak bisa dipakai. `declared` = coach menyatakan dirinya bisa jam itu →
        # kalau False, masih boleh dipilih tapi kasir wajib konfirmasi.
        row["available"] = (
            is_coach_available(c.id, bdate, start, end) if bdate else True
        )
        row["declared"] = (
            coach_declared_available(c.id, bdate, start, end) if bdate else True
        )
        out.append(row)

    max_p = (rate.max_persons if rate else 4) or 4
    return jsonify(
        rate=rate.to_dict() if rate else None,
        # harga per jam utk tiap jumlah peserta — biar POS tak perlu hitung sendiri
        price_per_hour={
            str(n): coaching_price_per_hour(rate, n) for n in range(1, max_p + 1)
        } if rate else {},
        count=len(out),
        coaches=out,
    ), 200


# ------------------------------------------------------------------
# Lapangan (facilities) & jadwal — M2
# ------------------------------------------------------------------
@pos_bp.get("/facilities")
@jwt_required()
def pos_facilities():
    terminal = _current_terminal()
    facilities = (
        Facility.query.filter_by(venue_id=terminal.venue_id, is_active=True)
        .order_by(Facility.name)
        .all()
    )
    # tanggal libur nasional dikirim supaya preview harga di POS bisa memakai
    # tarif 'holiday' (bukan cuma weekday/sabtu/minggu) — konsisten dgn backend.
    from .models import Holiday
    holidays = [h.date.isoformat() for h in Holiday.query.all()]
    return jsonify(
        count=len(facilities),
        facilities=[f.to_dict() for f in facilities],
        holidays=holidays,
    ), 200


@pos_bp.get("/facilities/<int:facility_id>/bookings")
@jwt_required()
def pos_facility_bookings(facility_id):
    """Booking pada 1 lapangan di tanggal tertentu (untuk cek ketersediaan)."""
    terminal = _current_terminal()
    facility = db.session.get(Facility, facility_id)
    if facility is None or facility.venue_id != terminal.venue_id:
        raise PosError("Lapangan tidak ditemukan", "not_found", 404)
    day = request.args.get("date")
    q = FacilityBooking.query.filter_by(facility_id=facility_id, status="booked")
    if day:
        q = q.filter_by(booking_date=day)
    bookings = q.order_by(FacilityBooking.start_time).all()
    # slot yg terkunci event (borong semua lapangan) pada venue+tanggal ini
    events = []
    if day:
        try:
            _d = datetime.strptime(day, "%Y-%m-%d").date()
            events = [
                {"start_time": e.start_time.strftime("%H:%M"), "end_time": e.end_time.strftime("%H:%M"), "name": e.name}
                for e in Event.query.filter(
                    Event.venue_id == facility.venue_id, Event.status == "active",
                    Event.date_from <= _d, Event.date_to >= _d,
                ).all()
            ]
        except ValueError:
            pass
    return jsonify(
        facility=facility.to_dict(),
        bookings=[b.to_dict() for b in bookings],
        events=events,
    ), 200


# ------------------------------------------------------------------
# Shift
# ------------------------------------------------------------------
@pos_bp.post("/shifts/open")
@jwt_required()
def shift_open():
    terminal = _current_terminal()
    data = request.get_json(silent=True) or {}
    shift = open_shift(
        terminal_id=terminal.id,
        venue_id=terminal.venue_id,
        cashier_id=int(get_jwt_identity()),
        opening_cash=data.get("opening_cash", 0),
    )
    return jsonify(shift=shift.to_dict()), 201


@pos_bp.get("/shifts/current")
@jwt_required()
def shift_current():
    terminal = _current_terminal()
    shift = Shift.query.filter_by(terminal_id=terminal.id, status="open").first()
    return jsonify(shift=shift.to_dict() if shift else None), 200


@pos_bp.post("/shifts/close")
@jwt_required()
def shift_close():
    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    data = request.get_json(silent=True) or {}
    if "counted_cash" not in data:
        raise PosError("counted_cash wajib diisi", "bad_request")
    shift = close_shift(
        shift,
        counted_cash=data.get("counted_cash"),
        deposit_amount=data.get("deposit_amount"),
        notes=data.get("notes"),
    )
    return jsonify(shift=shift.to_dict()), 200


@pos_bp.post("/shifts/cash-movement")
@jwt_required()
def shift_cash_movement():
    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    data = request.get_json(silent=True) or {}
    add_cash_movement(
        shift,
        mtype=data.get("type"),
        amount=data.get("amount", 0),
        reason=data.get("reason"),
        user_id=int(get_jwt_identity()),
    )
    return jsonify(shift=shift.to_dict()), 201


# ------------------------------------------------------------------
# Order & pembayaran
# ------------------------------------------------------------------
@pos_bp.post("/orders")
@jwt_required()
def order_create():
    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    data = request.get_json(silent=True) or {}
    order = create_order(shift, int(get_jwt_identity()), data)
    db.session.commit()
    return jsonify(order=order.to_dict()), 201


@pos_bp.post("/bookings/member")
@jwt_required()
def booking_member():
    """Booking member: 1 lapangan + jam SAMA, berulang di banyak tanggal (pola
    hari-dalam-minggu × rentang tanggal, mis. tiap Sen&Rab selama sebulan),
    jadi 1 order dgn diskon member (% atau Rp). Tanggal yg bentrok booking lain
    DILEWATI otomatis & dilaporkan. weekdays: list int 0=Senin..6=Minggu."""
    from datetime import timedelta
    from .services import _hours_between, _parse_time, is_slot_available
    from .models import Facility, facility_booking_price, day_type_for_date

    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    data = request.get_json(silent=True) or {}

    facility = db.session.get(Facility, data.get("facility_id"))
    if not facility or not facility.is_active or facility.venue_id != terminal.venue_id:
        raise PosError("Lapangan tidak ditemukan", "not_found", 404)

    weekdays = data.get("weekdays") or []
    if not isinstance(weekdays, list) or not weekdays:
        raise PosError("Pilih minimal 1 hari", "bad_request")
    try:
        d_from = date.fromisoformat(data["date_from"])
        d_to = date.fromisoformat(data["date_to"])
        start = _parse_time(data["start_time"])
        end = _parse_time(data["end_time"])
    except (KeyError, ValueError, TypeError):
        raise PosError("Tanggal/jam tidak valid", "bad_request")
    if d_to < d_from:
        raise PosError("Rentang tanggal terbalik", "bad_request")
    if (d_to - d_from).days > 120:
        raise PosError("Rentang maksimal 120 hari", "bad_request")
    hours = _hours_between(start, end)
    if hours <= 0:
        raise PosError("Jam selesai harus setelah jam mulai", "bad_booking_range")

    wd = {int(x) for x in weekdays}
    candidates, cur = [], d_from
    while cur <= d_to:
        if cur.weekday() in wd:
            candidates.append(cur)
        cur += timedelta(days=1)
    if not candidates:
        raise PosError("Tidak ada tanggal yang cocok dgn pola & rentang", "no_dates")

    booked, skipped = [], []
    for cd in candidates:
        (booked if is_slot_available(facility.id, cd, start, end) else skipped).append(cd)
    if not booked:
        raise PosError("Semua tanggal bentrok booking lain — tak ada yg bisa dibooking", "all_conflict", 409)

    items = [{
        "item_type": "booking", "facility_id": facility.id,
        "booking_date": cd.isoformat(), "start_time": data["start_time"], "end_time": data["end_time"],
    } for cd in booked]

    end_hour = start.hour + int(hours)
    # harga tiap sesi ikut kategori hari tanggalnya (weekday/sabtu/minggu/libur)
    # — subtotal = jumlah harga per-tanggal, BUKAN per_session flat × jumlah.
    per_date = [
        round(facility_booking_price(facility, start.hour, end_hour, day_type_for_date(cd)), 2)
        for cd in booked
    ]
    subtotal = round(sum(per_date), 2)
    per_session = per_date[0] if per_date else 0  # representatif (bisa beda antar hari)
    dtype = data.get("discount_type")
    dval = float(data.get("discount_value") or 0)
    if dtype == "percent":
        discount = round(subtotal * max(0.0, min(dval, 100.0)) / 100.0, 2)
    elif dtype == "amount":
        discount = max(0.0, dval)
    else:
        discount = 0.0
    discount = min(discount, subtotal)

    order = create_order(shift, int(get_jwt_identity()), {
        "items": items, "discount_amount": discount,
        "customer_name": data.get("customer_name"), "customer_phone": data.get("customer_phone"),
    })
    order.is_member = True  # penanda order booking member (utk CRM & laporan)
    db.session.commit()
    return jsonify(
        order=order.to_dict(),
        per_session=per_session,
        booked_dates=[c.isoformat() for c in booked],
        skipped_dates=[c.isoformat() for c in skipped],
    ), 201


@pos_bp.get("/orders/outstanding")
@jwt_required()
def orders_outstanding():
    """Order yang belum lunas di venue terminal — utk pelunasan. Termasuk
    'open' (belum dibayar sama sekali, mis. order dr Station Gaming yg
    sempat dibuat lewat STOP & Bayar tapi dialog pembayarannya ditutup
    tanpa bayar) DAN 'partial' (sudah DP)."""
    from .models import Order

    terminal = _current_terminal()
    orders = (
        Order.query.filter(
            Order.venue_id == terminal.venue_id,
            Order.status.in_(["open", "partial"]),
        )
        .order_by(Order.created_at.desc())
        .all()
    )
    # tanggal booking per order (dari FacilityBooking) → utk filter tanggal di POS
    item_ids = [it.id for o in orders for it in o.items]
    bd_map = {}  # order_item_id -> booking_date iso
    if item_ids:
        for oi_id, bdate in (
            db.session.query(FacilityBooking.order_item_id, FacilityBooking.booking_date)
            .filter(FacilityBooking.order_item_id.in_(item_ids)).all()
        ):
            if bdate:
                bd_map[oi_id] = bdate.isoformat()
    out = []
    for o in orders:
        d = o.to_dict()
        dates = sorted({bd_map[it.id] for it in o.items if it.id in bd_map})
        d["booking_dates"] = dates
        out.append(d)
    return jsonify(count=len(out), orders=out), 200


@pos_bp.get("/orders/<int:order_id>")
@jwt_required()
def order_get(order_id):
    from .models import Order

    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    return jsonify(order=order.to_dict()), 200


@pos_bp.post("/orders/<int:order_id>/items")
@jwt_required()
def order_add_items(order_id):
    """Tambah item ke bill (order) yang masih terbuka — open bill."""
    from .models import Order

    terminal = _current_terminal()
    _current_open_shift(terminal.id)  # wajib ada shift terbuka
    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    if order.venue_id != terminal.venue_id:
        raise PosError("Order bukan milik venue ini", "wrong_venue", 403)
    data = request.get_json(silent=True) or {}
    order = add_items_to_order(order, data.get("items") or [])
    return jsonify(order=order.to_dict()), 200


@pos_bp.post("/orders/<int:order_id>/reschedule")
@jwt_required()
def order_reschedule(order_id):
    """Pindah jadwal 1 slot booking ke slot baru (DP tetap, harga dihitung ulang)."""
    from .models import Order

    terminal = _current_terminal()
    _current_open_shift(terminal.id)  # wajib ada shift terbuka
    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    if order.venue_id != terminal.venue_id:
        raise PosError("Order bukan milik venue ini", "wrong_venue", 403)
    d = request.get_json(silent=True) or {}
    for f in ("facility_id", "booking_date", "start_time", "end_time"):
        if not d.get(f):
            return jsonify(error="bad_request", message=f"{f} wajib diisi"), 400
    order, info = reschedule_booking(
        order, d.get("order_item_id"), d["facility_id"],
        d["booking_date"], d["start_time"], d["end_time"], uid=int(get_jwt_identity()),
        coach_id=d.get("coach_id"),          # opsional: ganti coach
        coach_override=bool(d.get("coach_override")),
    )
    return jsonify(order=order.to_dict(), reschedule=info), 200


@pos_bp.post("/orders/<int:order_id>/pay")
@jwt_required()
def order_pay(order_id):
    from .models import Order

    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    if order.venue_id != terminal.venue_id:
        raise PosError("Order bukan milik venue ini", "wrong_venue", 403)
    data = request.get_json(silent=True) or {}
    # Bukti disimpan utk transfer, dan utk QRIS mode manual (BRIAPI belum aktif).
    if data.get("method") in ("transfer", "qris") and data.get("proof_image"):
        fn = _save_payment_proof(data["proof_image"])
        if not fn:
            raise PosError("Gagal simpan bukti (format/ukuran tak valid, maks 3MB)", "bad_proof")
        data["proof_filename"] = fn
    payment = pay_order(order, shift, int(get_jwt_identity()), data)
    return jsonify(order=order.to_dict(), payment=payment.to_dict()), 200


@pos_bp.post("/orders/<int:order_id>/pay-split")
@jwt_required()
def order_pay_split(order_id):
    """Split bill: bayar 1 order dengan BEBERAPA metode sekaligus (mis. sebagian
    cash, sebagian QRIS). Semua pembayaran dalam 1 transaksi (all-or-nothing).
    Setiap baris: {method, amount, reference?, proof_image?}."""
    from .models import Order

    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    if order.venue_id != terminal.venue_id:
        raise PosError("Order bukan milik venue ini", "wrong_venue", 403)
    body = request.get_json(silent=True) or {}
    splits = body.get("splits") or []
    if len(splits) < 2:
        raise PosError("Split minimal 2 metode.", "bad_split")
    # QRIS dinamis (BRIAPI aktif) tak bisa di-split (perlu QR per nominal, async)
    if briapi.is_configured() and any(s.get("method") == "qris" for s in splits):
        raise PosError("Split dengan QRIS dinamis belum didukung.", "qris_split_unsupported")
    uid = int(get_jwt_identity())
    try:
        for s in splits:
            data = {
                "method": s.get("method"),
                "amount": s.get("amount"),
                "reference": s.get("reference"),
            }
            if data["method"] in ("transfer", "qris") and s.get("proof_image"):
                fn = _save_payment_proof(s["proof_image"])
                if not fn:
                    raise PosError("Gagal simpan bukti (maks 3MB)", "bad_proof")
                data["proof_filename"] = fn
            pay_order(order, shift, uid, data, commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify(order=order.to_dict()), 200


@pos_bp.post("/orders/<int:order_id>/cancel")
@jwt_required()
def order_cancel(order_id):
    from .models import Order

    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not has_perm(user.role, "order.cancel"):
        raise PosError("Kasir tidak punya izin membatalkan transaksi — hubungi manajer", "forbidden", 403)

    terminal = _current_terminal()
    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    if order.venue_id != terminal.venue_id:
        raise PosError("Order bukan milik venue ini", "wrong_venue", 403)
    cancel_order(order, uid=user.id)
    return jsonify(order=order.to_dict()), 200


# ------------------------------------------------------------------
# Station Gaming (arena esport) — sesi main per stasiun, dioperasikan kasir.
# Data master station dikelola via /api/stations (portal admin/HO/manager).
# ------------------------------------------------------------------
@pos_bp.get("/stations")
@jwt_required()
def stations_list():
    from ..stations.models import GameSession, GameStation

    terminal = _current_terminal()
    stations = (
        GameStation.query.filter_by(venue_id=terminal.venue_id, is_active=True)
        .order_by(GameStation.tier, GameStation.code)
        .all()
    )
    active = {
        r.station_id: r
        for r in GameSession.query.filter(
            GameSession.station_id.in_([s.id for s in stations]), GameSession.status == "ongoing"
        ).all()
    } if stations else {}
    from .services import is_weekend
    from ..stations.models import reservations_today
    wknd = is_weekend(date.today())  # tarif weekday/weekend otomatis
    return jsonify(
        count=len(stations), weekend=wknd,
        stations=[s.to_dict(active.get(s.id), weekend=wknd) for s in stations],
        # reservasi hari ini yg belum dipakai — supaya kasir lihat langsung di
        # layar utama, tak perlu buka dialog reservasi dulu
        reservations_today=reservations_today(terminal.venue_id),
    ), 200


# ------------------------------------------------------------------
# Reservasi station — pesan di muka PER JENIS (unit ditentukan saat datang).
# Lihat migrasi 050 utk alasan per-jenis, bukan per-unit.
# ------------------------------------------------------------------
def _resv_parse(d):
    """(tanggal, mulai, selesai, menit) dari payload; lempar PosError kalau salah."""
    from ..stations.models import _resv_mins

    try:
        rdate = date.fromisoformat(d["date"])
        start = datetime.strptime(d["start_time"], "%H:%M").time()
        end = datetime.strptime(d["end_time"], "%H:%M").time()
    except (KeyError, ValueError, TypeError):
        raise PosError("Tanggal/jam tidak valid", "bad_time")
    minutes = _resv_mins(end, as_end=True) - _resv_mins(start)
    if minutes <= 0:
        raise PosError("Jam selesai harus setelah jam mulai", "bad_range")
    if rdate < date.today():
        raise PosError("Tanggal sudah lewat", "bad_date")
    return rdate, start, end, minutes


@pos_bp.get("/stations/types")
@jwt_required()
def station_types():
    """Jenis station di venue ini + kapasitas & tarif. Kalau diberi slot
    (date/start_time/end_time), tiap jenis dilengkapi sisa unit yg tersedia."""
    from ..stations.models import GameStation, station_type_usage
    from .services import is_weekend

    terminal = _current_terminal()
    rows = GameStation.query.filter_by(venue_id=terminal.venue_id, is_active=True).all()
    types = {}
    for s in rows:
        t = s.station_type or "Lainnya"
        g = types.setdefault(t, {"station_type": t, "capacity": 0, "rate": None, "units": []})
        g["capacity"] += 1
        g["units"].append({"id": s.id, "name": s.name})

    d = request.args.get("date")
    s_str, e_str = request.args.get("start_time"), request.args.get("end_time")
    slot = None
    if d and s_str and e_str:
        try:
            slot = _resv_parse({"date": d, "start_time": s_str, "end_time": e_str})
        except PosError:
            slot = None

    for t, g in types.items():
        # tarif jenis = tarif unit pertama (tarif per jenis memang seragam);
        # kalau nanti beda-beda, ambil yg terendah supaya perkiraan tak kelebihan
        unit_rates = [
            st.rate_for(is_weekend(slot[0] if slot else date.today()))
            for st in rows if (st.station_type or "Lainnya") == t
        ]
        g["rate"] = min(unit_rates) if unit_rates else 0
        if slot:
            rdate, start, end, _ = slot
            cap, used, detail = station_type_usage(terminal.venue_id, t, rdate, start, end)
            g["available"] = max(0, cap - used)
            g["used_detail"] = detail
    return jsonify(count=len(types), types=sorted(types.values(), key=lambda x: x["station_type"])), 200


@pos_bp.get("/stations/reservations")
@jwt_required()
def station_reservations_list():
    """Reservasi pd tanggal tertentu (default hari ini). Yg batal disembunyikan."""
    from ..stations.models import StationReservation

    terminal = _current_terminal()
    d_str = request.args.get("date") or date.today().isoformat()
    try:
        d = date.fromisoformat(d_str)
    except ValueError:
        raise PosError("Tanggal tidak valid", "bad_date")
    rows = (
        StationReservation.query.filter(
            StationReservation.venue_id == terminal.venue_id,
            StationReservation.reservation_date == d,
            StationReservation.status != "cancelled",
        )
        .order_by(StationReservation.start_time)
        .all()
    )
    out = []
    for r in rows:
        row = r.to_dict()
        o = db.session.get(Order, r.order_id) if r.order_id else None
        if o is not None:
            row["order_number"] = o.order_number
            row["order_total"] = float(o.total_amount or 0)
            row["order_paid"] = float(o.amount_paid or 0)
            row["order_due"] = round(float(o.total_amount or 0) - float(o.amount_paid or 0), 2)
            row["order_status"] = o.status
        out.append(row)
    return jsonify(date=d.isoformat(), count=len(out), reservations=out), 200


@pos_bp.post("/stations/reservations")
@jwt_required()
def station_reservation_create():
    """Buat reservasi + order berisi biaya durasi (prabayar, spt station_start).
    Pembayaran DP/lunas lewat /pos/orders/<id>/pay seperti order biasa."""
    from ..stations.models import StationReservation, station_type_usage

    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    d = request.get_json(silent=True) or {}
    stype = (d.get("station_type") or "").strip()
    if not stype:
        raise PosError("Jenis station wajib dipilih", "bad_request")
    rdate, start, end, minutes = _resv_parse(d)

    cap, used, _detail = station_type_usage(terminal.venue_id, stype, rdate, start, end)
    if cap <= 0:
        raise PosError(f"Tak ada unit aktif utk jenis {stype}", "no_unit", 404)
    if used >= cap:
        raise PosError(
            f"{stype} sudah penuh pada {rdate:%d/%m} {d['start_time']}-{d['end_time']} "
            f"({used}/{cap} terpakai)", "type_full", 409,
        )

    # tarif ikut jenis & kategori hari TANGGAL RESERVASI (bukan hari ini)
    from ..stations.models import GameStation
    from .services import is_weekend
    units = GameStation.query.filter_by(
        venue_id=terminal.venue_id, station_type=stype, is_active=True
    ).all()
    rate = min(u.rate_for(is_weekend(rdate)) for u in units)
    charge = round(minutes / 60 * float(rate), 2)

    order = create_order(shift, int(get_jwt_identity()), {
        "items": [{
            "item_type": "rental",
            "name": f"Reservasi {stype} {rdate:%d/%m} {d['start_time']}-{d['end_time']} ({minutes} menit)",
            "unit_price": charge, "quantity": 1,
        }],
        "customer_name": d.get("customer_name"),
        "customer_phone": d.get("customer_phone"),
    })
    resv = StationReservation(
        venue_id=terminal.venue_id, station_type=stype, reservation_date=rdate,
        start_time=start, end_time=end, duration_minutes=minutes,
        customer_name=d.get("customer_name"), customer_phone=d.get("customer_phone"),
        order_id=order.id, created_by=int(get_jwt_identity()),
    )
    db.session.add(resv)
    db.session.commit()
    return jsonify(reservation=resv.to_dict(), order=order.to_dict()), 201


@pos_bp.post("/stations/reservations/<int:rid>/start")
@jwt_required()
def station_reservation_start(rid):
    """Customer datang: kasir tentukan UNIT, sesi dibuat menaut order reservasi.

    Durasi sesi = durasi reservasi; jam mundur baru jalan saat tombol Play
    (jadi telat datang tak menggeser hitungan, sesuai keputusan). Order-nya
    dipakai ulang — station_stop sudah tahu sesi ber-order = prabayar, jadi
    biaya durasi TIDAK ditagih dua kali."""
    from ..stations.models import GameSession, GameStation, StationReservation
    from .services import is_weekend

    terminal = _current_terminal()
    _current_open_shift(terminal.id)
    resv = db.session.get(StationReservation, rid)
    if resv is None or resv.venue_id != terminal.venue_id:
        raise PosError("Reservasi tidak ditemukan", "not_found", 404)
    if resv.status != "booked":
        raise PosError("Reservasi sudah dipakai/dibatalkan", "bad_status", 409)

    d = request.get_json(silent=True) or {}
    station = db.session.get(GameStation, d.get("station_id"))
    if station is None or station.venue_id != terminal.venue_id or not station.is_active:
        raise PosError("Station tidak ditemukan", "not_found", 404)
    if (station.station_type or "Lainnya") != resv.station_type:
        raise PosError(
            f"Station ini bukan jenis {resv.station_type}", "wrong_type", 400
        )
    if GameSession.query.filter_by(station_id=station.id, status="ongoing").first():
        raise PosError("Station sedang dipakai", "in_use", 409)

    session = GameSession(
        station_id=station.id, venue_id=terminal.venue_id,
        customer_name=resv.customer_name,
        rate_per_hour=station.rate_for(is_weekend(resv.reservation_date)),
        booked_minutes=resv.duration_minutes,
        order_id=resv.order_id,      # <- prabayar: pakai order reservasi
        opened_by=int(get_jwt_identity()),
    )
    db.session.add(session)
    db.session.flush()
    resv.status = "fulfilled"
    resv.station_id = station.id
    resv.session_id = session.id
    db.session.commit()
    return jsonify(reservation=resv.to_dict(), session=session.to_dict()), 201


@pos_bp.post("/stations/reservations/<int:rid>/cancel")
@jwt_required()
def station_reservation_cancel(rid):
    """Batalkan reservasi (mis. no-show). Ordernya ikut di-void — DP yg sudah
    masuk tetap tercatat sbg DP hangus, sama spt pembatalan booking lapangan."""
    from ..stations.models import StationReservation

    terminal = _current_terminal()
    resv = db.session.get(StationReservation, rid)
    if resv is None or resv.venue_id != terminal.venue_id:
        raise PosError("Reservasi tidak ditemukan", "not_found", 404)
    if resv.status == "fulfilled":
        raise PosError("Reservasi sudah jadi sesi — hentikan sesinya, bukan batalkan reservasi", "bad_status", 409)
    order = db.session.get(Order, resv.order_id) if resv.order_id else None
    if order is not None and order.status != "void":
        cancel_order(order, uid=int(get_jwt_identity()))
    resv.status = "cancelled"
    db.session.commit()
    return jsonify(reservation=resv.to_dict()), 200


@pos_bp.post("/stations/<int:sid>/start")
@jwt_required()
def station_start(sid):
    from ..stations.models import GameSession, GameStation

    terminal = _current_terminal()
    station = db.session.get(GameStation, sid)
    if station is None or station.venue_id != terminal.venue_id or not station.is_active:
        raise PosError("Station tidak ditemukan", "not_found", 404)
    if GameSession.query.filter_by(station_id=sid, status="ongoing").first():
        raise PosError("Station sedang dipakai", "in_use", 409)
    data = request.get_json(silent=True) or {}
    try:
        booked_minutes = int(data.get("booked_minutes") or 0)
    except (TypeError, ValueError):
        booked_minutes = 0
    if booked_minutes <= 0:
        raise PosError("Durasi main (menit) wajib diisi", "bad_duration")
    from .services import is_weekend
    shift = _current_open_shift(terminal.id)  # butuh shift utk order durasi
    rate = station.rate_for(is_weekend(date.today()))  # tarif weekday/weekend hari ini
    session = GameSession(
        station_id=sid, venue_id=terminal.venue_id,
        customer_name=(data.get("customer_name") or None),
        rate_per_hour=rate, booked_minutes=booked_minutes,
        opened_by=int(get_jwt_identity()),
    )
    db.session.add(session)
    db.session.flush()
    # PRABAYAR: order durasi (running-tab) + add-on yg dipilih di awal, dibayar di depan.
    dur_charge = round(booked_minutes / 60 * float(rate), 2)
    items = [{
        "item_type": "rental",
        "name": f"Sewa {station.name} ({booked_minutes} menit)",
        "unit_price": dur_charge, "quantity": 1,
    }]
    from ..stations.models import GameAddon, GameSessionAddon
    for row in (data.get("addons") or []):
        addon = db.session.get(GameAddon, row.get("addon_id"))
        if addon is None or addon.venue_id != terminal.venue_id or not addon.is_active:
            raise PosError("Add-on tidak ditemukan", "not_found", 404)
        aqty = int(row.get("quantity") or 1)
        amin = int(row.get("booked_minutes") or 0)
        if aqty <= 0 or amin <= 0:
            raise PosError("Add-on: qty & durasi wajib > 0", "bad_addon")
        acharge = round(amin / 60 * float(addon.hourly_rate) * aqty, 2)
        db.session.add(GameSessionAddon(
            session_id=session.id, addon_id=addon.id, name_snapshot=addon.name,
            rate_per_hour=addon.hourly_rate, quantity=aqty, booked_minutes=amin,
            started_at=None, total_amount=acharge, created_by=int(get_jwt_identity()),
        ))
        items.append({
            "item_type": "rental",
            "name": f"Sewa {addon.name} x{aqty} ({amin} menit)",
            "unit_price": acharge, "quantity": 1,
        })
    order = create_order(shift, int(get_jwt_identity()), {
        "items": items, "customer_name": session.customer_name,
    })
    session.order_id = order.id
    db.session.commit()
    return jsonify(session=session.to_dict(), order=order.to_dict()), 201


@pos_bp.post("/stations/<int:sid>/play")
@jwt_required()
def station_play(sid):
    """Mulai MAIN (klik Play manual kasir): jalankan timer station + semua add-on
    yang belum jalan. Idempoten kalau sudah main."""
    terminal = _current_terminal()
    session = _current_ongoing_session(sid, terminal.venue_id)
    now = datetime.utcnow()
    if session.play_started_at is None:
        session.play_started_at = now
    for a in session.addons:
        if a.booked_minutes and a.booked_minutes > 0 and a.started_at is None:
            a.started_at = now
    db.session.commit()
    return jsonify(session=session.to_dict()), 200


def _current_ongoing_session(sid, venue_id):
    from ..stations.models import GameSession

    session = GameSession.query.filter_by(station_id=sid, status="ongoing").first()
    if session is None:
        raise PosError("Tidak ada sesi berjalan di station ini", "no_session", 409)
    if session.venue_id != venue_id:
        raise PosError("Station bukan milik venue ini", "wrong_venue", 403)
    return session


@pos_bp.post("/stations/<int:sid>/topup")
@jwt_required()
def station_topup(sid):
    from ..stations.models import GameSessionTopup

    terminal = _current_terminal()
    session = _current_ongoing_session(sid, terminal.venue_id)
    data = request.get_json(silent=True) or {}
    duration = data.get("duration_minutes")
    total = data.get("total_amount")
    if not duration or total in (None, ""):
        raise PosError("duration_minutes & total_amount wajib diisi", "bad_request")
    topup = GameSessionTopup(
        session_id=session.id, duration_minutes=int(duration),
        discount_amount=float(data.get("discount_amount") or 0),
        total_amount=float(total), created_by=int(get_jwt_identity()),
    )
    db.session.add(topup)
    db.session.flush()
    # PRABAYAR: tambah waktu ditagih saat itu → masuk ke order sesi (jadi partial).
    order = db.session.get(Order, session.order_id) if session.order_id else None
    if order is not None:
        order = add_items_to_order(order, [{
            "item_type": "rental",
            "name": f"Tambah waktu {int(duration)} menit — {session.station.name}",
            "unit_price": float(total), "quantity": 1,
        }])
    else:
        db.session.commit()  # sesi lama tanpa order → dibayar di stop (perilaku lama)
    # perpanjangan BOLEH walau menabrak reservasi — kasir cuma diperingatkan.
    # `topups` di-expire dulu: allocated_minutes() membaca koleksi itu, dan
    # topup yg baru ditambah tak otomatis masuk ke koleksi yg sudah ter-load.
    # Di produksi commit memang meng-expire semuanya, tapi jangan bergantung
    # pd efek samping itu — sekali add_items_to_order berubah, ini diam2 salah.
    from ..stations.models import topup_reservation_warning
    db.session.expire(session, ["topups"])
    warning = topup_reservation_warning(session, session.station)
    return jsonify(
        session=session.to_dict(),
        order=order.to_dict() if order else None,
        warning=warning,
    ), 201


@pos_bp.get("/addons")
@jwt_required()
def addons_list():
    from ..stations.models import GameAddon

    terminal = _current_terminal()
    addons = (
        GameAddon.query.filter_by(venue_id=terminal.venue_id, is_active=True)
        .order_by(GameAddon.name).all()
    )
    return jsonify(count=len(addons), addons=[a.to_dict() for a in addons]), 200


@pos_bp.post("/stations/<int:sid>/addons")
@jwt_required()
def station_addon_attach(sid):
    from ..stations.models import GameAddon, GameSessionAddon

    terminal = _current_terminal()
    session = _current_ongoing_session(sid, terminal.venue_id)
    data = request.get_json(silent=True) or {}
    addon = db.session.get(GameAddon, data.get("addon_id"))
    if addon is None or addon.venue_id != terminal.venue_id or not addon.is_active:
        raise PosError("Add-on tidak ditemukan", "not_found", 404)
    qty = int(data.get("quantity") or 1)
    if qty <= 0:
        raise PosError("Quantity harus > 0", "bad_quantity")
    try:
        booked_minutes = int(data.get("booked_minutes") or 0)
    except (TypeError, ValueError):
        booked_minutes = 0
    if booked_minutes <= 0:
        raise PosError("Durasi sewa add-on (menit) wajib diisi", "bad_duration")
    charge = round(booked_minutes / 60 * float(addon.hourly_rate) * qty, 2)
    # timer add-on mulai saat sesi sudah di-Play; kalau belum, mulai nanti pas Play
    sa = GameSessionAddon(
        session_id=session.id, addon_id=addon.id, name_snapshot=addon.name,
        rate_per_hour=addon.hourly_rate, quantity=qty,
        booked_minutes=booked_minutes,
        started_at=(datetime.utcnow() if session.play_started_at else None),
        total_amount=charge, created_by=int(get_jwt_identity()),
    )
    db.session.add(sa)
    db.session.flush()
    # PRABAYAR: biaya add-on ditagih saat itu → masuk ke order sesi (jadi partial)
    order = db.session.get(Order, session.order_id) if session.order_id else None
    if order is not None:
        order = add_items_to_order(order, [{
            "item_type": "rental",
            "name": f"Sewa {addon.name} x{qty} ({booked_minutes} menit)",
            "unit_price": charge, "quantity": 1,
        }])
    else:
        db.session.commit()  # sesi lama tanpa order → ditagih di stop (perilaku lama)
    return jsonify(session=session.to_dict(), order=order.to_dict() if order else None), 201


@pos_bp.delete("/stations/<int:sid>/addons/<int:said>")
@jwt_required()
def station_addon_detach(sid, said):
    from ..stations.models import GameSessionAddon

    terminal = _current_terminal()
    session = _current_ongoing_session(sid, terminal.venue_id)
    sa = db.session.get(GameSessionAddon, said)
    if sa is None or sa.session_id != session.id:
        raise PosError("Add-on pada sesi ini tidak ditemukan", "not_found", 404)
    if sa.booked_minutes and sa.booked_minutes > 0:
        raise PosError("Add-on prabayar sudah dibayar — tak bisa dilepas", "prepaid_locked", 409)
    db.session.delete(sa)
    db.session.commit()
    return jsonify(session=session.to_dict()), 200


@pos_bp.post("/stations/<int:sid>/fnb")
@jwt_required()
def station_fnb_adjust(sid):
    """Tambah/kurangi pesanan F&B yg menempel ke sesi (disimpan di server,
    tak hilang walau dialog ditutup). body: product_id + delta (default +1;
    kirim -1 utk kurangi). Qty jadi <=0 → baris dihapus. Harga & stok final
    dihitung ulang saat stop (create_order), snapshot di sini utk tampilan."""
    from ..stations.models import GameSessionFnb
    from .promos import active_promo, effective_unit_price

    terminal = _current_terminal()
    session = _current_ongoing_session(sid, terminal.venue_id)
    data = request.get_json(silent=True) or {}
    product = db.session.get(Product, data.get("product_id"))
    if product is None or not product.is_active or product.venue_id != terminal.venue_id:
        raise PosError("Produk tidak ditemukan", "not_found", 404)
    try:
        delta = int(data.get("delta", 1))
    except (TypeError, ValueError):
        delta = 1
    if delta == 0:
        return jsonify(session=session.to_dict()), 200

    row = next((f for f in session.fnb_items if f.product_id == product.id), None)
    if row is None:
        if delta < 0:
            return jsonify(session=session.to_dict()), 200
        row = GameSessionFnb(
            session_id=session.id, product_id=product.id, name_snapshot=product.name[:120],
            unit_price=effective_unit_price(product, active_promo(product.id)),
            quantity=delta, created_by=int(get_jwt_identity()),
        )
        db.session.add(row)
    else:
        row.quantity += delta
        if row.quantity <= 0:
            db.session.delete(row)
    db.session.commit()
    return jsonify(session=session.to_dict()), 200


@pos_bp.post("/stations/<int:sid>/stop")
@jwt_required()
def station_stop(sid):
    """Stop sesi lalu LANGSUNG gabung jadi 1 Order (biaya waktu + semua topup,
    + F&B tambahan kalau ada di 'extra_items') — order status 'open' (belum
    lunas), lanjut bayar lewat /pos/orders/<id>/pay spt order biasa."""
    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    session = _current_ongoing_session(sid, terminal.venue_id)
    station = session.station

    session.status = "stopped"
    session.stopped_at = datetime.utcnow()

    data = request.get_json(silent=True) or {}
    billable_minutes = session._billable_minutes()
    # F&B ditagih di AKHIR. Add-on PRABAYAR (booked_minutes>0) sudah dibayar saat
    # ditempel → tak ditagih lagi; add-on LAMA (booked_minutes 0) ikut durasi sesi.
    end_items = []
    for a in session.addons:
        if a.booked_minutes and a.booked_minutes > 0:
            continue  # prabayar, sudah lunas
        charge = round(billable_minutes / 60 * float(a.rate_per_hour) * a.quantity, 2)
        end_items.append({
            "item_type": "rental",
            "name": f"{a.name_snapshot} x{a.quantity} ({billable_minutes} menit)",
            "unit_price": charge, "quantity": 1,
        })
    for f in session.fnb_items:
        if f.product_id:
            end_items.append({"item_type": "product", "product_id": f.product_id, "quantity": f.quantity})
    end_items.extend(data.get("extra_items") or [])

    order = db.session.get(Order, session.order_id) if session.order_id else None
    if order is not None:
        # sesi PRABAYAR: durasi sudah lunas di order ini; tambah F&B/add-on saja.
        if end_items:
            order = add_items_to_order(order, end_items)  # order jadi partial (sisa = F&B/add-on)
        else:
            db.session.commit()  # tak ada tambahan → order sudah lunas
    else:
        # sesi LAMA (tanpa order prabayar) → bangun order penuh (durasi+topup+F&B) spt dulu
        base_minutes = session.elapsed_minutes() if session._is_legacy() else int(session.booked_minutes)
        items = [{
            "item_type": "rental", "name": f"Sewa {station.name} ({base_minutes} menit)",
            "unit_price": session.time_charge(), "quantity": 1,
        }]
        for t in session.topups:
            items.append({
                "item_type": "rental", "name": f"Tambah waktu {t.duration_minutes} menit — {station.name}",
                "unit_price": float(t.total_amount), "quantity": 1,
            })
        items.extend(end_items)
        order = create_order(shift, int(get_jwt_identity()), {
            "items": items, "customer_name": session.customer_name,
        })
        session.order_id = order.id
        db.session.commit()
    return jsonify(session=session.to_dict(), order=order.to_dict()), 200


# ==================================================================
# QRIS BRIAPI — layar bayar (polling status) & notifikasi dari bank
# ==================================================================
def _qris_payload(p: Payment) -> dict:
    """Data yang dibutuhkan layar bayar QRIS di POS."""
    return {
        "payment_id": p.id,
        "order_id": p.order_id,
        "amount": float(p.amount),
        "status": p.status,
        "qr_content": p.qr_content,
        "qr_expires_at": p.qr_expires_at.isoformat() if p.qr_expires_at else None,
        "bri_reference_no": p.bri_reference_no,
    }


@pos_bp.get("/payments/<int:payment_id>/qris")
@jwt_required()
def qris_status(payment_id):
    """Status QRIS untuk layar bayar. Dipanggil berulang (polling) oleh POS.

    Murni baca dari DB — murah, karena webhook-lah yang biasanya lebih dulu
    mengubah status. Kalau QR sudah lewat masa berlaku, ditandai kedaluwarsa.
    """
    p = db.session.get(Payment, payment_id)
    if p is None or p.method != "qris":
        raise PosError("Pembayaran QRIS tidak ditemukan", "not_found", 404)

    before = p.status
    expire_stale_qris(p)
    if p.status != before:
        db.session.commit()
    return jsonify(_qris_payload(p)), 200


@pos_bp.post("/payments/<int:payment_id>/qris/sync")
@jwt_required()
def qris_sync(payment_id):
    """Paksa tanya status ke BRI (tombol "Cek status" / cadangan bila webhook telat)."""
    p = Payment.query.filter_by(id=payment_id).with_for_update().first()
    if p is None or p.method != "qris":
        raise PosError("Pembayaran QRIS tidak ditemukan", "not_found", 404)

    sync_qris_payment(p)
    expire_stale_qris(p)
    db.session.commit()
    return jsonify(_qris_payload(p)), 200


def _snap_reply(code, message, http=200):
    return jsonify(responseCode=code, responseMessage=message), http


@pos_bp.post("/webhook/bri")
def bri_webhook():
    """Notifikasi pembayaran QRIS dari BRI (MPM Notifikasi).

    Endpoint publik (tanpa JWT) — karena itu pengamanannya berlapis:
      1. tanda tangan RSA BRI wajib valid (diverifikasi dgn public key BRI);
         CATATAN: BRI hanya menandatangani `clientId|timestamp`, BUKAN isi body —
         jadi lapis 3-5 di bawah bukan pelengkap, tapi pengaman utama isi pesan;
      2. timestamp harus segar → notifikasi lama tak bisa diputar ulang;
      3. baris payment dikunci (FOR UPDATE) → webhook & polling tak bisa
         sama-sama mengkredit;
      4. nominal notifikasi harus sama persis dgn nominal payment;
      5. konfirmasi idempoten → kiriman ulang tidak menambah uang.
    Semua penolakan dicatat di log dengan alasannya.
    """
    raw = request.get_data()  # byte mentah — tanda tangan dihitung atas ini,
    body_str = raw.decode("utf-8", errors="replace")  # bukan hasil re-serialize
    ts = request.headers.get("X-TIMESTAMP", "")
    sig = request.headers.get("X-SIGNATURE", "")

    if not briapi.is_configured():
        log.warning("Webhook BRI masuk tapi kredensial belum diatur — ditolak")
        return _snap_reply("5005200", "Service unavailable", 503)

    if not briapi.verify_notification(ts, sig):
        log.warning("Webhook BRI: tanda tangan tidak valid (ip=%s)", request.remote_addr)
        return _snap_reply("4015200", "Unauthorized. Invalid signature", 401)

    if not _timestamp_fresh(ts):
        log.warning("Webhook BRI: timestamp basi/tak terbaca (%s)", ts)
        return _snap_reply("4005200", "Bad Request. Stale timestamp", 400)

    try:
        data = json.loads(body_str)
    except ValueError:
        return _snap_reply("4005200", "Bad Request. Invalid JSON", 400)

    ref_partner = data.get("originalPartnerReferenceNo") or data.get("partnerReferenceNo")
    ref_bank = data.get("originalReferenceNo") or data.get("referenceNo")

    q = Payment.query.filter_by(method="qris")
    if ref_partner:
        q = q.filter_by(external_id=ref_partner)
    elif ref_bank:
        q = q.filter_by(bri_reference_no=ref_bank)
    else:
        return _snap_reply("4005200", "Bad Request. Missing reference", 400)

    payment = q.with_for_update().first()  # kunci baris sampai transaksi selesai
    if payment is None:
        log.warning("Webhook BRI: payment tak ditemukan (partner=%s bank=%s)",
                    ref_partner, ref_bank)
        return _snap_reply("4045200", "Transaction not found", 404)

    status = briapi.normalize_status(data.get("latestTransactionStatus"))

    if status == "paid":
        # Nominal WAJIB cocok — jangan pernah percaya angka dari luar begitu saja.
        notified = (data.get("amount") or {}).get("value")
        if not _amount_matches(notified, payment.amount):
            log.error(
                "Webhook BRI: nominal beda utk payment #%s (notifikasi=%s, sistem=%s) — DITOLAK",
                payment.id, notified, payment.amount,
            )
            db.session.rollback()
            return _snap_reply("4045201", "Amount mismatch", 404)

        changed = confirm_qris_payment(payment, ref_bank)
        db.session.commit()
        log.info("Webhook BRI: payment #%s lunas (baru=%s)", payment.id, changed)
    elif status == "failed":
        if payment.status == "pending":
            payment.status = "failed"
        db.session.commit()
    else:
        db.session.rollback()  # masih pending — tak ada yang perlu disimpan

    return _snap_reply("2005200", "Request has been processed successfully")


def _timestamp_fresh(ts: str, tolerance_seconds: int = 600) -> bool:
    """Tolak notifikasi yang timestamp-nya jauh dari sekarang (anti putar-ulang)."""
    try:
        sent = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return False
    if sent.tzinfo is None:
        return False  # SNAP mewajibkan offset zona
    delta = abs((datetime.now(timezone.utc) - sent).total_seconds())
    return delta <= tolerance_seconds


def _amount_matches(notified_value, payment_amount) -> bool:
    """Bandingkan nominal sebagai Decimal (hindari jebakan pembulatan float)."""
    if notified_value in (None, ""):
        return False
    try:
        return Decimal(str(notified_value)) == Decimal(str(payment_amount))
    except (InvalidOperation, TypeError):
        return False


# ======================================================================
# EVENT (borong semua lapangan) — turnamen/sewa besar. Migration 064.
# ======================================================================
def _hhmm(s):
    return datetime.strptime(s, "%H:%M").time()


def _mins_ev(t, as_end=False):
    m = t.hour * 60 + t.minute
    return 24 * 60 if (as_end and m == 0) else m


def _venue_facilities(venue_id):
    return Facility.query.filter_by(venue_id=venue_id, is_active=True).all()


def _event_quote(venue_id, date_from, date_to, start_t, end_t):
    """Harga usulan = tarif normal semua lapangan × jam × jumlah hari."""
    facs = _venue_facilities(venue_id)
    sh, eh = start_t.hour, (end_t.hour if end_t.hour != 0 else 24)
    total = 0.0
    d = date_from
    while d <= date_to:
        dt = day_type_for_date(d)
        for f in facs:
            total += float(facility_booking_price(f, sh, eh, dt))
        d += timedelta(days=1)
    return round(total, 2), len(facs)


def _event_conflicts(venue_id, date_from, date_to, start_t, end_t, exclude_event_order_id=None):
    """Booking (member/reguler) yang bentrok dgn jam event pd rentang tanggal."""
    fac_ids = [f.id for f in Facility.query.filter_by(venue_id=venue_id).all()]
    if not fac_ids:
        return []
    e_min, s_min = _mins_ev(end_t, as_end=True), _mins_ev(start_t)
    rows = (
        FacilityBooking.query.filter(
            FacilityBooking.facility_id.in_(fac_ids),
            FacilityBooking.booking_date >= date_from,
            FacilityBooking.booking_date <= date_to,
            FacilityBooking.status == "booked",
        ).all()
    )
    fac_names = {f.id: f.name for f in Facility.query.filter(Facility.id.in_(fac_ids)).all()}
    out = []
    for b in rows:
        if not (_mins_ev(b.start_time) < e_min and _mins_ev(b.end_time, as_end=True) > s_min):
            continue
        oi = db.session.get(OrderItem, b.order_item_id) if b.order_item_id else None
        order = oi.order if oi else None
        if order is None or order.status == "void":
            continue
        if exclude_event_order_id and order.id == exclude_event_order_id:
            continue
        out.append({
            "booking_id": b.id,
            "order_id": order.id,
            "order_item_id": b.order_item_id,
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "is_member": order.is_member,
            "status": order.status,
            "facility_name": fac_names.get(b.facility_id),
            "booking_date": b.booking_date.isoformat(),
            "start_time": b.start_time.strftime("%H:%M"),
            "end_time": b.end_time.strftime("%H:%M"),
        })
    out.sort(key=lambda x: (x["booking_date"], x["start_time"]))
    return out


@pos_bp.get("/events/quote")
@jwt_required()
def event_quote():
    terminal = _current_terminal()
    try:
        df = datetime.strptime(request.args["date_from"], "%Y-%m-%d").date()
        dt = datetime.strptime(request.args["date_to"], "%Y-%m-%d").date()
        st = _hhmm(request.args["start_time"])
        et = _hhmm(request.args["end_time"])
    except (KeyError, ValueError):
        raise PosError("Parameter tanggal/jam tidak lengkap/valid", "bad_params")
    if dt < df:
        raise PosError("Tanggal selesai sebelum tanggal mulai", "bad_range")
    price, n_fac = _event_quote(terminal.venue_id, df, dt, st, et)
    conflicts = _event_conflicts(terminal.venue_id, df, dt, st, et)
    return jsonify(suggested_price=price, facility_count=n_fac, conflict_count=len(conflicts)), 200


@pos_bp.post("/events")
@jwt_required()
def event_create():
    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        raise PosError("Nama event wajib", "bad_name")
    try:
        df = datetime.strptime(d["date_from"], "%Y-%m-%d").date()
        dto = datetime.strptime(d["date_to"], "%Y-%m-%d").date()
        st = _hhmm(d["start_time"])
        et = _hhmm(d["end_time"])
    except (KeyError, ValueError):
        raise PosError("Tanggal/jam tidak lengkap/valid", "bad_params")
    if dto < df:
        raise PosError("Tanggal selesai sebelum tanggal mulai", "bad_range")
    if _mins_ev(et, as_end=True) <= _mins_ev(st):
        raise PosError("Jam selesai harus setelah jam mulai", "bad_time")
    price = _D(d.get("price"))
    if price < 0:
        raise PosError("Harga tidak valid", "bad_price")

    venue = db.session.get(Venue, terminal.venue_id)
    uid = int(get_jwt_identity())
    label = f"Sewa Event: {name} ({df.isoformat()}"
    label += f"–{dto.isoformat()}" if dto != df else ""
    label += f" {st.strftime('%H:%M')}-{et.strftime('%H:%M')})"

    order = Order(
        order_number=generate_order_number(venue), venue_id=venue.id,
        terminal_id=terminal.id, shift_id=shift.id, cashier_id=uid,
        customer_name=(d.get("renter") or name), status="open",
        subtotal=price, discount_amount=0, total_amount=price, amount_paid=0,
    )
    order.items.append(OrderItem(
        item_type="event", name_snapshot=label[:120], unit_price=price,
        quantity=1, line_total=price,
    ))
    db.session.add(order)
    db.session.flush()

    ev = Event(
        venue_id=venue.id, name=name, renter=d.get("renter"), phone=d.get("phone"),
        date_from=df, date_to=dto, start_time=st, end_time=et, price=price,
        order_id=order.id, status="active", notes=d.get("notes"), created_by=uid,
    )
    db.session.add(ev)

    # pembayaran opsional (DP/lunas). amount 0 / kosong = belum bayar → Pelunasan.
    pay = d.get("payment") or {}
    amt = _D(pay.get("amount"))
    if pay.get("method") and amt > 0:
        pdata = {"method": pay.get("method"), "amount": amt, "reference": pay.get("reference")}
        if pdata["method"] in ("transfer", "qris") and pay.get("proof_image"):
            fn = _save_payment_proof(pay["proof_image"])
            if not fn:
                raise PosError("Gagal simpan bukti (maks 3MB)", "bad_proof")
            pdata["proof_filename"] = fn
        pay_order(order, shift, uid, pdata)  # commit di dalam
    else:
        db.session.commit()

    conflicts = _event_conflicts(venue.id, df, dto, st, et, exclude_event_order_id=order.id)
    return jsonify(event=ev.to_dict(), order=order.to_dict(), conflicts=conflicts), 201


@pos_bp.get("/events")
@jwt_required()
def event_list():
    terminal = _current_terminal()
    q = Event.query.filter(Event.venue_id == terminal.venue_id, Event.status == "active")
    frm = request.args.get("date_from")
    if frm:
        try:
            q = q.filter(Event.date_to >= datetime.strptime(frm, "%Y-%m-%d").date())
        except ValueError:
            pass
    else:
        q = q.filter(Event.date_to >= date.today())
    events = q.order_by(Event.date_from).all()
    return jsonify(events=[e.to_dict() for e in events]), 200


@pos_bp.get("/events/<int:event_id>")
@jwt_required()
def event_detail(event_id):
    ev = db.session.get(Event, event_id)
    if not ev:
        raise PosError("Event tidak ditemukan", "not_found", 404)
    conflicts = _event_conflicts(ev.venue_id, ev.date_from, ev.date_to, ev.start_time, ev.end_time,
                                 exclude_event_order_id=ev.order_id)
    return jsonify(event=ev.to_dict(), conflicts=conflicts), 200


@pos_bp.post("/events/<int:event_id>/cancel")
@jwt_required()
def event_cancel(event_id):
    ev = db.session.get(Event, event_id)
    if not ev:
        raise PosError("Event tidak ditemukan", "not_found", 404)
    ev.status = "cancelled"
    db.session.commit()
    return jsonify(message="Event dibatalkan (jadwal terbuka kembali).", event=ev.to_dict()), 200
