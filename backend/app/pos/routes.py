"""Endpoint POS — Fase M1. Prefix: /api/pos"""
from datetime import date, datetime

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
from ..security import verify_password
from .models import Attendance, Facility, FacilityBooking, Order, OrderItem, PosTerminal, Product, ProductCategory, Shift
from .services import (
    PosError,
    add_cash_movement,
    cancel_order,
    close_shift,
    create_order,
    open_shift,
    pay_order,
)

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
    row = Attendance.query.filter_by(user_id=user.id, date=today).first()
    if row is None:
        row = Attendance(
            user_id=user.id, employee_id=user.employee_id,
            venue_id=terminal.venue_id, terminal_id=terminal.id, date=today,
        )
        db.session.add(row)

    # lokasi GPS (opsional — "lat,lon" dari geolocation browser), verifikasi
    # absen dilakukan di luar/lokasi venue, bukan bukti wajib
    location = (data.get("location") or "").strip()[:100] or None

    if action == "in":
        if row.check_in:
            return jsonify(error="already", message=f"{name} sudah absen masuk hari ini "
                           f"({row.check_in.strftime('%H:%M')})"), 409
        row.check_in = now
        row.check_in_location = location
    else:
        if row.check_out:
            return jsonify(error="already", message=f"{name} sudah absen pulang hari ini "
                           f"({row.check_out.strftime('%H:%M')})"), 409
        row.check_out = now
        row.check_out_location = location

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
_REPORT_LABELS = {"ticket": "Tiket Masuk", "booking": "Booking Lapangan", "rental": "Station Gaming"}


@pos_bp.get("/reports/category-daily")
@jwt_required()
def report_category_daily():
    terminal = _current_terminal()
    today = date.today()

    order_ids = [
        oid
        for (oid,) in Order.query.filter(
            Order.venue_id == terminal.venue_id,
            Order.status == "paid",
            func.date(Order.created_at) == today,
        ).with_entities(Order.id).all()
    ]

    groups = {}
    total = 0.0
    if order_ids:
        cat_names = {c.id: c.name for c in ProductCategory.query.all()}
        rows = (
            db.session.query(
                OrderItem.item_type,
                Product.category_id,
                func.coalesce(func.sum(OrderItem.quantity), 0),
                func.coalesce(func.sum(OrderItem.line_total), 0),
            )
            .outerjoin(Product, OrderItem.product_id == Product.id)
            .filter(OrderItem.order_id.in_(order_ids))
            .group_by(OrderItem.item_type, Product.category_id)
            .all()
        )
        for item_type, category_id, qty, amount in rows:
            if item_type == "product":
                label = cat_names.get(category_id, "Tanpa Kategori")
            else:
                label = _REPORT_LABELS.get(item_type, item_type)
            g = groups.setdefault(label, {"category": label, "qty": 0.0, "amount": 0.0})
            g["qty"] += float(qty)
            g["amount"] += float(amount)
            total += float(amount)

    by_category = sorted(groups.values(), key=lambda x: -x["amount"])
    return jsonify(
        date=today.isoformat(),
        order_count=len(order_ids),
        total=round(total, 2),
        by_category=by_category,
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
    return jsonify(count=len(facilities), facilities=[f.to_dict() for f in facilities]), 200


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
    return jsonify(
        facility=facility.to_dict(),
        bookings=[b.to_dict() for b in bookings],
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


@pos_bp.get("/orders/outstanding")
@jwt_required()
def orders_outstanding():
    """Booking/order yang belum lunas (DP) di venue terminal — untuk pelunasan."""
    from .models import Order

    terminal = _current_terminal()
    orders = (
        Order.query.filter_by(venue_id=terminal.venue_id, status="partial")
        .order_by(Order.created_at.desc())
        .all()
    )
    return jsonify(count=len(orders), orders=[o.to_dict() for o in orders]), 200


@pos_bp.get("/orders/<int:order_id>")
@jwt_required()
def order_get(order_id):
    from .models import Order

    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    return jsonify(order=order.to_dict()), 200


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
    payment = pay_order(order, shift, int(get_jwt_identity()), data)
    return jsonify(order=order.to_dict(), payment=payment.to_dict()), 200


@pos_bp.post("/orders/<int:order_id>/cancel")
@jwt_required()
def order_cancel(order_id):
    from .models import Order

    terminal = _current_terminal()
    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    if order.venue_id != terminal.venue_id:
        raise PosError("Order bukan milik venue ini", "wrong_venue", 403)
    cancel_order(order)
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
    return jsonify(count=len(stations), stations=[s.to_dict(active.get(s.id)) for s in stations]), 200


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
    session = GameSession(
        station_id=sid, venue_id=terminal.venue_id,
        customer_name=(data.get("customer_name") or None),
        rate_per_hour=station.hourly_rate, opened_by=int(get_jwt_identity()),
    )
    db.session.add(session)
    db.session.commit()
    return jsonify(session=session.to_dict()), 201


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
    db.session.commit()
    return jsonify(session=session.to_dict()), 201


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
    sa = GameSessionAddon(
        session_id=session.id, addon_id=addon.id, name_snapshot=addon.name,
        rate_per_hour=addon.hourly_rate, quantity=qty, created_by=int(get_jwt_identity()),
    )
    db.session.add(sa)
    db.session.commit()
    return jsonify(session=session.to_dict()), 201


@pos_bp.delete("/stations/<int:sid>/addons/<int:said>")
@jwt_required()
def station_addon_detach(sid, said):
    from ..stations.models import GameSessionAddon

    terminal = _current_terminal()
    session = _current_ongoing_session(sid, terminal.venue_id)
    sa = db.session.get(GameSessionAddon, said)
    if sa is None or sa.session_id != session.id:
        raise PosError("Add-on pada sesi ini tidak ditemukan", "not_found", 404)
    db.session.delete(sa)
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
    items = [{
        "item_type": "rental", "name": f"Sewa {station.name} ({session.elapsed_minutes()} menit)",
        "unit_price": session.time_charge(), "quantity": 1,
    }]
    for t in session.topups:
        items.append({
            "item_type": "rental", "name": f"Tambah waktu {t.duration_minutes} menit — {station.name}",
            "unit_price": float(t.total_amount), "quantity": 1,
        })
    for a in session.addons:
        # add-on ditagih per jam mengikuti durasi sesi utama (sama basis dgn elapsed_minutes di atas)
        charge = round(session.elapsed_minutes() / 60 * float(a.rate_per_hour) * a.quantity, 2)
        items.append({
            "item_type": "rental",
            "name": f"{a.name_snapshot} x{a.quantity} ({session.elapsed_minutes()} menit)",
            "unit_price": charge, "quantity": 1,
        })
    items.extend(data.get("extra_items") or [])

    order = create_order(shift, int(get_jwt_identity()), {
        "items": items, "customer_name": session.customer_name,
    })
    session.order_id = order.id
    db.session.commit()
    return jsonify(session=session.to_dict(), order=order.to_dict()), 200
