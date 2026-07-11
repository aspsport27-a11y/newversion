"""Endpoint admin — kelola master data + laporan. Prefix: /api/admin

Akses: admin & head_office (kelola); reports juga manager_unit.
"""
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import User, Venue
from ..security import (
    ROLE_ADMIN,
    ROLE_HEAD_OFFICE,
    ROLE_MANAGER,
    hash_password,
    roles_required,
)
from ..pos.models import (
    Facility,
    FacilityBooking,
    Order,
    OrderItem,
    Payment,
    PosTerminal,
    Product,
    ProductCategory,
    Shift,
)

admin_bp = Blueprint("admin", __name__)

MANAGE = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE)
VIEW = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)


def _err(msg, code="bad_request", status=400):
    return jsonify(error=code, message=msg), status


def _venue_or_404(venue_id):
    v = db.session.get(Venue, venue_id) if venue_id else None
    return v


def _D(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ==================================================================
# VENUES
# ==================================================================
@admin_bp.get("/venues")
@jwt_required()
@VIEW
def venues():
    vs = Venue.query.order_by(Venue.code).all()
    return jsonify(venues=[v.to_dict() for v in vs]), 200


# ==================================================================
# PRODUCTS
# ==================================================================
@admin_bp.get("/products")
@jwt_required()
@VIEW
def products_list():
    q = Product.query
    vid = request.args.get("venue_id", type=int)
    if vid:
        q = q.filter_by(venue_id=vid)
    items = q.order_by(Product.venue_id, Product.name).all()
    return jsonify(count=len(items), products=[p.to_dict() for p in items]), 200


@admin_bp.post("/products")
@jwt_required()
@MANAGE
def products_create():
    d = request.get_json(silent=True) or {}
    for f in ("sku", "name", "venue_id"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    if not _venue_or_404(d["venue_id"]):
        return _err("Venue tidak ditemukan", "not_found", 404)
    if Product.query.filter_by(sku=d["sku"]).first():
        return _err("SKU sudah dipakai", "duplicate", 409)
    cat_id = None
    if d.get("category"):
        cat = ProductCategory.query.filter_by(name=d["category"]).first()
        if not cat:
            cat = ProductCategory(name=d["category"], kind=d.get("kind", "other"))
            db.session.add(cat)
            db.session.flush()
        cat_id = cat.id
    p = Product(
        sku=d["sku"], name=d["name"], venue_id=d["venue_id"], category_id=cat_id,
        price=_D(d.get("price")), unit=d.get("unit", "pcs"),
        track_stock=bool(d.get("track_stock", True)), stock_qty=int(d.get("stock_qty", 0) or 0),
        is_active=bool(d.get("is_active", True)),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(product=p.to_dict()), 201


@admin_bp.put("/products/<int:pid>")
@jwt_required()
@MANAGE
def products_update(pid):
    p = db.session.get(Product, pid)
    if not p:
        return _err("Produk tidak ditemukan", "not_found", 404)
    d = request.get_json(silent=True) or {}
    if "name" in d:
        p.name = d["name"]
    if "price" in d:
        p.price = _D(d["price"])
    if "unit" in d:
        p.unit = d["unit"]
    if "track_stock" in d:
        p.track_stock = bool(d["track_stock"])
    if "stock_qty" in d:
        p.stock_qty = int(d["stock_qty"] or 0)
    if "is_active" in d:
        p.is_active = bool(d["is_active"])
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(product=p.to_dict()), 200


# ==================================================================
# FACILITIES (lapangan)
# ==================================================================
@admin_bp.get("/facilities")
@jwt_required()
@VIEW
def facilities_list():
    q = Facility.query
    vid = request.args.get("venue_id", type=int)
    if vid:
        q = q.filter_by(venue_id=vid)
    items = q.order_by(Facility.venue_id, Facility.name).all()
    return jsonify(count=len(items), facilities=[f.to_dict() for f in items]), 200


def _parse_time(s, default):
    try:
        return datetime.strptime(s, "%H:%M").time()
    except (TypeError, ValueError):
        return default


@admin_bp.post("/facilities")
@jwt_required()
@MANAGE
def facilities_create():
    d = request.get_json(silent=True) or {}
    for f in ("name", "venue_id"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    if not _venue_or_404(d["venue_id"]):
        return _err("Venue tidak ditemukan", "not_found", 404)
    fac = Facility(
        venue_id=d["venue_id"], name=d["name"], type=d.get("type"),
        hourly_rate=_D(d.get("hourly_rate")),
        open_time=_parse_time(d.get("open_time"), datetime.strptime("08:00", "%H:%M").time()),
        close_time=_parse_time(d.get("close_time"), datetime.strptime("23:00", "%H:%M").time()),
        is_active=bool(d.get("is_active", True)),
    )
    db.session.add(fac)
    db.session.commit()
    return jsonify(facility=fac.to_dict()), 201


@admin_bp.put("/facilities/<int:fid>")
@jwt_required()
@MANAGE
def facilities_update(fid):
    fac = db.session.get(Facility, fid)
    if not fac:
        return _err("Lapangan tidak ditemukan", "not_found", 404)
    d = request.get_json(silent=True) or {}
    if "name" in d:
        fac.name = d["name"]
    if "type" in d:
        fac.type = d["type"]
    if "hourly_rate" in d:
        fac.hourly_rate = _D(d["hourly_rate"])
    if "open_time" in d:
        fac.open_time = _parse_time(d["open_time"], fac.open_time)
    if "close_time" in d:
        fac.close_time = _parse_time(d["close_time"], fac.close_time)
    if "is_active" in d:
        fac.is_active = bool(d["is_active"])
    db.session.commit()
    return jsonify(facility=fac.to_dict()), 200


# ==================================================================
# TERMINALS
# ==================================================================
@admin_bp.get("/terminals")
@jwt_required()
@VIEW
def terminals_list():
    items = PosTerminal.query.order_by(PosTerminal.venue_id, PosTerminal.code).all()
    return jsonify(terminals=[t.to_dict() for t in items]), 200


@admin_bp.post("/terminals")
@jwt_required()
@MANAGE
def terminals_create():
    d = request.get_json(silent=True) or {}
    for f in ("code", "name", "venue_id"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    if PosTerminal.query.filter_by(code=d["code"]).first():
        return _err("Kode terminal sudah dipakai", "duplicate", 409)
    t = PosTerminal(code=d["code"], name=d["name"], venue_id=d["venue_id"], is_active=True)
    db.session.add(t)
    db.session.commit()
    return jsonify(terminal=t.to_dict()), 201


# ==================================================================
# CASHIERS (users role staff)
# ==================================================================
@admin_bp.get("/cashiers")
@jwt_required()
@MANAGE
def cashiers_list():
    users = User.query.filter_by(role="staff").order_by(User.username).all()
    return jsonify(cashiers=[u.to_dict() for u in users]), 200


@admin_bp.post("/cashiers")
@jwt_required()
@MANAGE
def cashiers_create():
    d = request.get_json(silent=True) or {}
    for f in ("username", "email", "pin"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    if len(str(d["pin"])) < 4:
        return _err("PIN minimal 4 digit")
    if User.query.filter((User.username == d["username"]) | (User.email == d["email"])).first():
        return _err("Username/email sudah dipakai", "duplicate", 409)
    u = User(
        username=d["username"], email=d["email"], role="staff",
        active=True, venue_id=d.get("venue_id"),
    )
    u.set_password(str(d["pin"]))
    u.pin_hash = hash_password(str(d["pin"]))
    db.session.add(u)
    db.session.commit()
    return jsonify(cashier=u.to_dict()), 201


@admin_bp.post("/cashiers/<int:uid>/pin")
@jwt_required()
@MANAGE
def cashiers_set_pin(uid):
    u = db.session.get(User, uid)
    if not u:
        return _err("User tidak ditemukan", "not_found", 404)
    d = request.get_json(silent=True) or {}
    if len(str(d.get("pin", ""))) < 4:
        return _err("PIN minimal 4 digit")
    u.pin_hash = hash_password(str(d["pin"]))
    db.session.commit()
    return jsonify(message="PIN diperbarui"), 200


# ==================================================================
# REPORTS
# ==================================================================
def _date_range():
    today = date.today().isoformat()
    d_from = request.args.get("from") or today
    d_to = request.args.get("to") or today
    return d_from, d_to


@admin_bp.get("/reports/sales")
@jwt_required()
@VIEW
def report_sales():
    d_from, d_to = _date_range()
    vid = request.args.get("venue_id", type=int)

    base = Order.query.filter(Order.status == "paid")
    base = base.filter(func.date(Order.created_at).between(d_from, d_to))
    if vid:
        base = base.filter(Order.venue_id == vid)

    order_ids = [o.id for o in base.with_entities(Order.id).all()]
    total_revenue = float(
        base.with_entities(func.coalesce(func.sum(Order.total_amount), 0)).scalar() or 0
    )
    order_count = len(order_ids)

    by_method, by_type, daily = [], [], []
    if order_ids:
        # per metode bayar
        for method, amt in (
            db.session.query(Payment.method, func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.order_id.in_(order_ids), Payment.status == "paid")
            .group_by(Payment.method)
            .all()
        ):
            by_method.append({"method": method, "amount": float(amt)})
        # per jenis item
        for itype, amt in (
            db.session.query(OrderItem.item_type, func.coalesce(func.sum(OrderItem.line_total), 0))
            .filter(OrderItem.order_id.in_(order_ids))
            .group_by(OrderItem.item_type)
            .all()
        ):
            by_type.append({"item_type": itype, "amount": float(amt)})
        # harian
        for day, amt, cnt in (
            db.session.query(
                func.date(Order.created_at),
                func.coalesce(func.sum(Order.total_amount), 0),
                func.count(Order.id),
            )
            .filter(Order.id.in_(order_ids))
            .group_by(func.date(Order.created_at))
            .order_by(func.date(Order.created_at))
            .all()
        ):
            daily.append({"date": str(day), "revenue": float(amt), "orders": int(cnt)})

    return jsonify(
        range={"from": d_from, "to": d_to},
        total_revenue=total_revenue,
        order_count=order_count,
        by_method=by_method,
        by_item_type=by_type,
        daily=daily,
    ), 200


@admin_bp.get("/reports/shifts")
@jwt_required()
@VIEW
def report_shifts():
    d_from, d_to = _date_range()
    vid = request.args.get("venue_id", type=int)
    q = Shift.query.filter(func.date(Shift.opened_at).between(d_from, d_to))
    if vid:
        q = q.filter(Shift.venue_id == vid)
    shifts = q.order_by(Shift.opened_at.desc()).all()
    # peta username kasir
    uids = {s.cashier_id for s in shifts}
    users = {u.id: u.username for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}
    rows = []
    for s in shifts:
        row = s.to_dict()
        row["cashier"] = users.get(s.cashier_id)
        rows.append(row)
    return jsonify(range={"from": d_from, "to": d_to}, count=len(rows), shifts=rows), 200


@admin_bp.get("/bookings")
@jwt_required()
@VIEW
def bookings_list():
    """Daftar booking lapangan + info order (customer)."""
    from datetime import timedelta

    today = date.today()
    d_from = request.args.get("from") or today.isoformat()
    d_to = request.args.get("to") or (today + timedelta(days=30)).isoformat()
    vid = request.args.get("venue_id", type=int)
    fid = request.args.get("facility_id", type=int)

    q = (
        db.session.query(FacilityBooking, Facility, Order)
        .join(Facility, FacilityBooking.facility_id == Facility.id)
        .outerjoin(OrderItem, FacilityBooking.order_item_id == OrderItem.id)
        .outerjoin(Order, OrderItem.order_id == Order.id)
        .filter(FacilityBooking.booking_date.between(d_from, d_to))
    )
    if vid:
        q = q.filter(FacilityBooking.venue_id == vid)
    if fid:
        q = q.filter(FacilityBooking.facility_id == fid)
    q = q.order_by(FacilityBooking.booking_date, FacilityBooking.start_time)

    rows = []
    for fb, fac, order in q.all():
        row = fb.to_dict()
        row["facility_name"] = fac.name
        row["venue_id"] = fb.venue_id
        row["order_number"] = order.order_number if order else None
        row["customer_name"] = order.customer_name if order else None
        row["order_status"] = order.status if order else None
        rows.append(row)
    return jsonify(range={"from": d_from, "to": d_to}, count=len(rows), bookings=rows), 200
