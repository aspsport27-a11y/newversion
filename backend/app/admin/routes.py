"""Endpoint admin — kelola master data + laporan. Prefix: /api/admin

Akses: admin & head_office (kelola); reports juga manager_unit.
"""
import calendar
import math
import secrets
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import Area, DeletedOrderLog, Employee, EmployeeDebt, KasbonRequest, ShiftAdjustLog, ShiftReopenLog, Supplier, User, Venue
from ..security import (
    ROLE_ADMIN,
    ROLE_ADMIN_UNIT,
    ROLE_HEAD_OFFICE,
    ROLE_MANAGER,
    hash_password,
    require_perm,
    roles_required,
)
from ..pos.models import (
    DAY_TYPES,
    Attendance,
    Coach,
    CoachingRate,
    Event,
    EventContact,
    Facility,
    FacilityBooking,
    FacilityRateRule,
    Holiday,
    Order,
    OrderItem,
    Payment,
    PosTerminal,
    Product,
    ProductCategory,
    Promo,
    Shift,
    StockMovement,
)
from ..ops.models import OpRequest
from ..payroll.models import PayrollRun
from ..proc.models import PurchaseOrder

admin_bp = Blueprint("admin", __name__)

# RBAC configurable (izin dikelola via /admin/permissions)
# master.manage dipecah per-resource supaya bisa dikasih granular, mis. admin_unit
# hanya boleh kelola produk/lapangan/promo tanpa venue/area/setup.
VENUE_MANAGE = require_perm("venue.manage")
AREA_MANAGE = require_perm("area.manage")
PRODUCT_MANAGE = require_perm("product.manage")
PROMO_MANAGE = require_perm("promo.manage")
FACILITY_MANAGE = require_perm("facility.manage")
SETUP_MANAGE = require_perm("setup.manage")
ORDER_CANCEL = require_perm("order.cancel")
VIEW = require_perm("master.view")
REPORT_SALES = require_perm("report.sales")
# HR: manager unit juga boleh kelola karyawan (venue-nya sendiri)
MANAGE_HR = require_perm("hr.manage")

POSITIONS = ["Manager", "Ass Manajer/SPV", "Kasir", "Staff Lapangan", "Lifeguard", "Cleaning", "Admin"]


def _current_user():
    return db.session.get(User, int(get_jwt_identity()))


def _forced_venue():
    """Manager unit dibatasi ke venue-nya; admin/head_office bebas (None)."""
    u = _current_user()
    if u and u.role == ROLE_MANAGER:
        return u.venue_id
    return None


def _report_scope():
    """Venue-id yang boleh dilihat di laporan (list) atau None (semua, admin/HO).
    manager -> [venue]; admin_unit -> venue area. Kalau minta 1 venue yang SAH
    dalam cakupan, dipersempit ke venue itu; kalau di luar cakupan, diabaikan."""
    vids = _scope_vids(_current_user())  # None=all, list=scoped
    req = request.args.get("venue_id", type=int)
    if vids is None:
        return [req] if req else None
    if not vids:
        return []  # tak punya venue (mis. admin_unit belum di-set area)
    if req and req in vids:
        return [req]
    return vids


def _scope_vids(u):
    """Venue yang boleh dikelola user utk master data (produk/lapangan/promo).
    None = semua (admin/head_office). manager_unit -> [venue-nya].
    admin_unit -> venue2 di areanya (bisa kosong bila belum di-set area)."""
    if not u:
        return []
    if u.role == ROLE_MANAGER:
        return [u.venue_id] if u.venue_id else []
    if u.role == ROLE_ADMIN_UNIT:
        return [v.id for v in Venue.query.filter_by(area_id=u.area_id).all()] if u.area_id else []
    return None


def _err(msg, code="bad_request", status=400):
    return jsonify(error=code, message=msg), status


def _venue_or_404(venue_id):
    v = db.session.get(Venue, venue_id) if venue_id else None
    return v


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _D(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _promo(v):
    """Harga promo: None jika kosong/0."""
    try:
        return float(v) if v not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return None


# ==================================================================
# VENUES
# ==================================================================
@admin_bp.get("/venues")
@jwt_required()
@VIEW
def venues():
    # Batasi ke cakupan user: admin/HO semua; manajer venue-nya; admin_unit
    # venue di areanya. Jadi semua dropdown venue otomatis "sesuai area".
    vids = _scope_vids(_current_user())
    q = Venue.query
    if vids is not None:
        q = q.filter(Venue.id.in_(vids)) if vids else q.filter(db.false())
    vs = q.order_by(Venue.code).all()
    return jsonify(venues=[v.to_dict() for v in vs]), 200


def _cap(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


@admin_bp.post("/venues")
@jwt_required()
@VENUE_MANAGE
def venues_create():
    d = request.get_json(silent=True) or {}
    for f in ("code", "name", "type"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    if Venue.query.filter_by(code=d["code"]).first():
        return _err("Kode venue sudah dipakai", "duplicate", 409)
    v = Venue(
        code=d["code"], name=d["name"], type=d["type"], address=d.get("address"),
        city=d.get("city"), phone=d.get("phone"), email=d.get("email"),
        capacity=_cap(d.get("capacity")), active=bool(d.get("active", True)),
    )
    db.session.add(v)
    db.session.commit()
    return jsonify(venue=v.to_dict()), 201


@admin_bp.put("/venues/<int:vid>")
@jwt_required()
@VENUE_MANAGE
def venues_update(vid):
    v = db.session.get(Venue, vid)
    if not v:
        return _err("Venue tidak ditemukan", "not_found", 404)
    d = request.get_json(silent=True) or {}
    if "code" in d and d["code"] != v.code:
        if Venue.query.filter_by(code=d["code"]).first():
            return _err("Kode venue sudah dipakai", "duplicate", 409)
        v.code = d["code"]
    for f in ("name", "type", "address", "city", "phone", "email"):
        if f in d:
            setattr(v, f, d[f])
    if "capacity" in d:
        v.capacity = _cap(d["capacity"])
    if "active" in d:
        v.active = bool(d["active"])
    if "area_id" in d:
        v.area_id = d["area_id"] or None
    v.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(venue=v.to_dict()), 200


@admin_bp.delete("/venues/<int:vid>")
@jwt_required()
@VENUE_MANAGE
def venues_delete(vid):
    v = db.session.get(Venue, vid)
    if not v:
        return _err("Venue tidak ditemukan", "not_found", 404)
    deps = {
        "order": Order.query.filter_by(venue_id=vid).count(),
        "produk": Product.query.filter_by(venue_id=vid).count(),
        "lapangan": Facility.query.filter_by(venue_id=vid).count(),
        "terminal": PosTerminal.query.filter_by(venue_id=vid).count(),
    }
    blocking = {k: c for k, c in deps.items() if c > 0}
    if blocking:
        detail = ", ".join(f"{k} ({c})" for k, c in blocking.items())
        return _err(
            f"Venue punya data terkait: {detail}. Nonaktifkan saja (jangan hapus).",
            "has_dependencies", 409,
        )
    db.session.delete(v)
    db.session.commit()
    return jsonify(message="Venue dihapus"), 200


# ==================================================================
# AREA (kumpulan venue) — utk scope role admin_unit. Kelola: admin/HO.
# ==================================================================
@admin_bp.get("/areas")
@jwt_required()
@VIEW
def areas_list():
    areas = Area.query.order_by(Area.code).all()
    counts = dict(
        db.session.query(Venue.area_id, func.count(Venue.id))
        .filter(Venue.area_id.isnot(None)).group_by(Venue.area_id).all()
    )
    return jsonify(areas=[a.to_dict(venue_count=counts.get(a.id, 0)) for a in areas]), 200


@admin_bp.post("/areas")
@jwt_required()
@AREA_MANAGE
def areas_create():
    d = request.get_json(silent=True) or {}
    code = (d.get("code") or "").strip().upper()
    name = (d.get("name") or "").strip()
    if not code or not name:
        return _err("Kode & nama area wajib")
    if Area.query.filter_by(code=code).first():
        return _err("Kode area sudah dipakai", "duplicate", 409)
    a = Area(code=code, name=name, is_active=d.get("is_active", True))
    db.session.add(a)
    db.session.commit()
    return jsonify(area=a.to_dict(venue_count=0)), 201


@admin_bp.put("/areas/<int:aid>")
@jwt_required()
@AREA_MANAGE
def areas_update(aid):
    a = db.session.get(Area, aid)
    if not a:
        return _err("Area tidak ditemukan", "not_found", 404)
    d = request.get_json(silent=True) or {}
    if "code" in d and d["code"]:
        code = d["code"].strip().upper()
        if code != a.code and Area.query.filter_by(code=code).first():
            return _err("Kode area sudah dipakai", "duplicate", 409)
        a.code = code
    if "name" in d and d["name"]:
        a.name = d["name"].strip()
    if "is_active" in d:
        a.is_active = bool(d["is_active"])
    db.session.commit()
    return jsonify(area=a.to_dict()), 200


@admin_bp.delete("/areas/<int:aid>")
@jwt_required()
@AREA_MANAGE
def areas_delete(aid):
    a = db.session.get(Area, aid)
    if not a:
        return _err("Area tidak ditemukan", "not_found", 404)
    nv = Venue.query.filter_by(area_id=aid).count()
    nu = User.query.filter_by(area_id=aid).count()
    if nv or nu:
        return _err(
            f"Area masih dipakai: {nv} venue, {nu} user. Lepaskan dulu.",
            "has_dependencies", 409,
        )
    db.session.delete(a)
    db.session.commit()
    return jsonify(message="Area dihapus"), 200


# ==================================================================
# RBAC — matriks izin per role (configurable). Kelola: HANYA admin (hard),
# supaya tak bisa mengunci diri sendiri lewat toggle.
# ==================================================================
ADMIN_ONLY = roles_required(ROLE_ADMIN)


@admin_bp.get("/permissions")
@jwt_required()
@ADMIN_ONLY
def permissions_get():
    from ..perms import EDITABLE_ROLES, PERMISSIONS, grants_matrix
    return jsonify(
        permissions=[{"code": c, "label": l, "category": cat} for c, l, cat in PERMISSIONS],
        roles=[{"code": r, "label": l} for r, l in EDITABLE_ROLES],
        grants=grants_matrix(),
    ), 200


@admin_bp.post("/permissions")
@jwt_required()
@ADMIN_ONLY
def permissions_set():
    from ..perms import EDITABLE_ROLES, PERMISSION_CODES, set_grant
    d = request.get_json(silent=True) or {}
    role = d.get("role")
    code = d.get("code")
    granted = bool(d.get("granted"))
    editable = {r for r, _ in EDITABLE_ROLES}
    if role not in editable:
        return _err("Role tidak bisa diubah")
    if code not in PERMISSION_CODES:
        return _err("Kode izin tidak dikenal")
    set_grant(role, code, granted)
    return jsonify(ok=True, role=role, code=code, granted=granted), 200


# ==================================================================
# HARI LIBUR (holidays) — tanggal dihitung 'weekend' utk harga tiket
# ==================================================================
@admin_bp.get("/holidays")
@jwt_required()
@VIEW
def holidays_list():
    year = request.args.get("year", type=int)
    q = Holiday.query
    if year:
        from datetime import date as _d
        q = q.filter(Holiday.date >= _d(year, 1, 1), Holiday.date <= _d(year, 12, 31))
    items = q.order_by(Holiday.date).all()
    return jsonify(holidays=[h.to_dict() for h in items]), 200


@admin_bp.post("/holidays")
@jwt_required()
@FACILITY_MANAGE
def holidays_create():
    d = request.get_json(silent=True) or {}
    ds = (d.get("date") or "").strip()
    if not ds:
        return _err("Tanggal wajib diisi")
    try:
        dt = date.fromisoformat(ds)
    except ValueError:
        return _err("Format tanggal salah (YYYY-MM-DD)")
    if Holiday.query.filter_by(date=dt).first():
        return _err("Tanggal sudah ada", "duplicate", 409)
    h = Holiday(date=dt, name=(d.get("name") or "").strip() or None)
    db.session.add(h)
    db.session.commit()
    return jsonify(holiday=h.to_dict()), 201


@admin_bp.delete("/holidays/<int:hid>")
@jwt_required()
@FACILITY_MANAGE
def holidays_delete(hid):
    h = db.session.get(Holiday, hid)
    if not h:
        return _err("Hari libur tidak ditemukan", "not_found", 404)
    db.session.delete(h)
    db.session.commit()
    return jsonify(message="Dihapus"), 200


# ==================================================================
# PRODUCTS
# ==================================================================
@admin_bp.get("/product-categories")
@jwt_required()
@VIEW
def product_categories_list():
    cats = ProductCategory.query.filter_by(is_active=True).order_by(ProductCategory.name).all()
    return jsonify(categories=[{"id": c.id, "name": c.name} for c in cats]), 200


@admin_bp.get("/products")
@jwt_required()
@VIEW
def products_list():
    q = Product.query
    vid = request.args.get("venue_id", type=int)
    vids = _scope_vids(_current_user())
    if vid:
        if vids is not None and vid not in vids:
            return _err("Venue di luar cakupan Anda", "forbidden", 403)
        q = q.filter_by(venue_id=vid)
    elif vids is not None:
        q = q.filter(Product.venue_id.in_(vids)) if vids else q.filter(db.false())
    # filter jenis: ?ticket=1 (hanya tiket) / ?ticket=0 (hanya F&B) / tanpa = semua
    tk = request.args.get("ticket")
    if tk == "1":
        q = q.filter(Product.is_ticket.is_(True))
    elif tk == "0":
        q = q.filter(Product.is_ticket.is_(False))
    from ..pos.promos import product_public

    items = q.order_by(Product.venue_id, Product.name).all()
    cat_names = {c.id: c.name for c in ProductCategory.query.all()}
    out = []
    for p in items:
        d = product_public(p)
        d["category_name"] = cat_names.get(p.category_id)
        out.append(d)
    return jsonify(count=len(out), products=out), 200


def _gen_sku(venue):
    """SKU otomatis: KODEVENUE-NNN, dijamin unik."""
    base = (venue.code or "PRD").upper().replace(" ", "")
    n = Product.query.filter_by(venue_id=venue.id).count() + 1
    while True:
        sku = f"{base}-{n:03d}"
        if not Product.query.filter_by(sku=sku).first():
            return sku
        n += 1


@admin_bp.post("/products")
@jwt_required()
@PRODUCT_MANAGE
def products_create():
    d = request.get_json(silent=True) or {}
    for f in ("name", "venue_id"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    venue = _venue_or_404(d["venue_id"])
    if not venue:
        return _err("Venue tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and venue.id not in vids:
        return _err("Venue di luar cakupan Anda", "forbidden", 403)
    # SKU otomatis (kalau tak diberikan / kosong)
    sku = (d.get("sku") or "").strip() or _gen_sku(venue)
    if Product.query.filter_by(sku=sku).first():
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
        sku=sku, name=d["name"], venue_id=d["venue_id"], category_id=cat_id,
        price=_D(d.get("price")), promo_price=_promo(d.get("promo_price")),
        unit=d.get("unit", "pcs"),
        track_stock=bool(d.get("track_stock", True)), stock_qty=int(d.get("stock_qty", 0) or 0),
        min_stock=int(d.get("min_stock", 0) or 0),
        supplier_id=d.get("supplier_id") or None,
        is_ticket=bool(d.get("is_ticket", False)),
        open_price=bool(d.get("open_price", False)),
        weekend_price=_promo(d.get("weekend_price")),
        is_consignment=bool(d.get("is_consignment", False)),
        consignment_price=_promo(d.get("consignment_price")),
        is_active=bool(d.get("is_active", True)),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(product=p.to_dict()), 201


@admin_bp.put("/products/<int:pid>")
@jwt_required()
@PRODUCT_MANAGE
def products_update(pid):
    p = db.session.get(Product, pid)
    if not p:
        return _err("Produk tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and p.venue_id not in vids:
        return _err("Bukan produk venue cakupan Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    if "name" in d:
        p.name = d["name"]
    if "price" in d:
        p.price = _D(d["price"])
    if "promo_price" in d:
        p.promo_price = _promo(d["promo_price"])
    if "unit" in d:
        p.unit = d["unit"]
    if "track_stock" in d:
        p.track_stock = bool(d["track_stock"])
    if "stock_qty" in d:
        p.stock_qty = int(d["stock_qty"] or 0)
    if "min_stock" in d:
        p.min_stock = int(d["min_stock"] or 0)
    if "supplier_id" in d:
        p.supplier_id = d["supplier_id"] or None
    if "category" in d:
        cat_name = (d["category"] or "").strip()
        if cat_name:
            cat = ProductCategory.query.filter_by(name=cat_name).first()
            if not cat:
                cat = ProductCategory(name=cat_name, kind="other")
                db.session.add(cat)
                db.session.flush()
            p.category_id = cat.id
        else:
            p.category_id = None
    if "is_ticket" in d:
        p.is_ticket = bool(d["is_ticket"])
    if "open_price" in d:
        p.open_price = bool(d["open_price"])
    if "weekend_price" in d:
        p.weekend_price = _promo(d["weekend_price"])
    if "is_consignment" in d:
        p.is_consignment = bool(d["is_consignment"])
    if "consignment_price" in d:
        p.consignment_price = _promo(d["consignment_price"])
    if "is_active" in d:
        p.is_active = bool(d["is_active"])
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(product=p.to_dict()), 200


@admin_bp.delete("/products/<int:pid>")
@jwt_required()
@PRODUCT_MANAGE
def products_delete(pid):
    from ..proc.models import PurchaseOrderItem

    p = db.session.get(Product, pid)
    if not p:
        return _err("Produk tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and p.venue_id not in vids:
        return _err("Bukan produk venue cakupan Anda", "forbidden", 403)
    deps = {
        "order": OrderItem.query.filter_by(product_id=pid).count(),
        "PO": PurchaseOrderItem.query.filter_by(product_id=pid).count(),
        "riwayat stok": StockMovement.query.filter_by(product_id=pid).count(),
    }
    blocking = {k: c for k, c in deps.items() if c > 0}
    if blocking:
        detail = ", ".join(f"{k} ({c})" for k, c in blocking.items())
        return _err(
            f"Produk punya riwayat terkait: {detail}. Nonaktifkan saja (jangan hapus).",
            "has_dependencies", 409,
        )
    db.session.delete(p)  # promo terkait ikut terhapus (ondelete=CASCADE)
    db.session.commit()
    return jsonify(message="Produk dihapus"), 200


@admin_bp.post("/products/bulk-min-stock")
@jwt_required()
@PRODUCT_MANAGE
def products_bulk_min_stock():
    """Isi ambang stok minimum (min_stock) sekaligus utk banyak produk —
    percepat setup awal 'Stok Menipis'. Default hanya isi yang belum diatur
    (min_stock 0/kosong), supaya nilai yg sudah dikustom user tak tertimpa."""
    d = request.get_json(silent=True) or {}
    try:
        min_stock = int(d.get("min_stock"))
    except (TypeError, ValueError):
        return _err("min_stock wajib berupa angka")
    if min_stock <= 0:
        return _err("min_stock harus lebih dari 0")
    overwrite = bool(d.get("overwrite", False))
    venue_id = d.get("venue_id")

    vids = _scope_vids(_current_user())
    q = Product.query.filter(Product.is_active.is_(True), Product.track_stock.is_(True))
    if venue_id:
        venue_id = int(venue_id)
        if vids is not None and venue_id not in vids:
            return _err("Venue di luar cakupan Anda", "forbidden", 403)
        q = q.filter(Product.venue_id == venue_id)
    elif vids is not None:
        q = q.filter(Product.venue_id.in_(vids)) if vids else q.filter(db.false())
    if not overwrite:
        q = q.filter(db.or_(Product.min_stock.is_(None), Product.min_stock == 0))

    updated = q.update({Product.min_stock: min_stock}, synchronize_session=False)
    db.session.commit()
    return jsonify(updated=updated), 200


@admin_bp.post("/products/import")
@jwt_required()
@PRODUCT_MANAGE
def products_import():
    """Import produk massal dari CSV (percepat entry data awal). Kolom:
    name,price,unit,category,stock_qty,min_stock,track_stock,supplier_code
    Hanya 'name' wajib; SKU dibuat otomatis per venue seperti entry manual."""
    import csv
    import io

    vid = request.args.get("venue_id", type=int)
    if not vid:
        return _err("venue_id wajib")
    venue = _venue_or_404(vid)
    if not venue:
        return _err("Venue tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and venue.id not in vids:
        return _err("Venue di luar cakupan Anda", "forbidden", 403)
    f = request.files.get("file")
    if not f:
        return _err("File CSV wajib diunggah")
    try:
        text = f.stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return _err("File harus CSV teks (UTF-8)")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return _err("File CSV kosong atau tanpa header")
    reader.fieldnames = [(fn or "").strip().lower() for fn in reader.fieldnames]

    created, skipped = 0, []
    for i, raw in enumerate(reader, start=2):  # baris 1 = header
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        name = row.get("name")
        if not name:
            skipped.append({"row": i, "reason": "kolom 'name' kosong"})
            continue

        cat_id = None
        if row.get("category"):
            cat = ProductCategory.query.filter_by(name=row["category"]).first()
            if not cat:
                cat = ProductCategory(name=row["category"], kind="other")
                db.session.add(cat)
                db.session.flush()
            cat_id = cat.id

        supplier_id = None
        if row.get("supplier_code"):
            sup = Supplier.query.filter_by(supplier_code=row["supplier_code"]).first()
            supplier_id = sup.id if sup else None

        track_raw = row.get("track_stock", "")
        track_stock = track_raw.lower() not in ("0", "false", "tidak", "no") if track_raw else True

        p = Product(
            sku=_gen_sku(venue), name=name, venue_id=vid, category_id=cat_id,
            price=_D(row.get("price")), unit=row.get("unit") or "pcs",
            track_stock=track_stock,
            stock_qty=_int(row.get("stock_qty")),
            min_stock=_int(row.get("min_stock")),
            supplier_id=supplier_id, is_active=True,
        )
        db.session.add(p)
        db.session.flush()  # supaya _gen_sku baris berikutnya tak tabrakan
        created += 1

    db.session.commit()
    return jsonify(created=created, skipped=skipped), 200


# ==================================================================
# EMPLOYEES (karyawan) + kasbon
# ==================================================================
def _emp_debt_balance(emp_id):
    adv = (
        db.session.query(func.coalesce(func.sum(EmployeeDebt.amount), 0))
        .filter_by(employee_id=emp_id, type="advance").scalar() or 0
    )
    rep = (
        db.session.query(func.coalesce(func.sum(EmployeeDebt.amount), 0))
        .filter_by(employee_id=emp_id, type="repayment").scalar() or 0
    )
    return round(float(adv) - float(rep), 2)


def _gen_employee_code():
    n = (db.session.query(func.count(Employee.id)).scalar() or 0) + 1
    code = f"EMP-{n:04d}"
    while Employee.query.filter_by(employee_id=code).first():
        n += 1
        code = f"EMP-{n:04d}"
    return code


def _emp_account(emp_id):
    return User.query.filter_by(employee_id=emp_id).first()


@admin_bp.get("/employees")
@jwt_required()
@VIEW
def employees_list():
    q = Employee.query
    forced = _forced_venue()
    vid = forced if forced is not None else request.args.get("venue_id", type=int)
    if vid:
        q = q.filter_by(venue_id=vid)
    rows = []
    for e in q.order_by(Employee.name).all():
        d = e.to_dict()
        d["debt_balance"] = _emp_debt_balance(e.id)
        acc = _emp_account(e.id)
        d["has_account"] = acc is not None
        d["username"] = acc.username if acc else None
        rows.append(d)
    return jsonify(count=len(rows), employees=rows, positions=POSITIONS), 200


@admin_bp.post("/employees")
@jwt_required()
@MANAGE_HR
def employees_create():
    d = request.get_json(silent=True) or {}
    if not d.get("name"):
        return _err("Nama wajib diisi")
    forced = _forced_venue()
    venue_id = forced if forced is not None else d.get("venue_id")
    if not venue_id:
        return _err("venue wajib dipilih")
    e = Employee(
        employee_id=d.get("employee_id") or _gen_employee_code(),
        name=d["name"], position=d.get("position"), venue_id=venue_id,
        salary=_promo(d.get("salary")), kasbon_installment=_promo(d.get("kasbon_installment")),
        allowance=_promo(d.get("allowance")), bank_account=d.get("bank_account"),
        bank_name=d.get("bank_name"), phone=d.get("phone"), email=d.get("email"),
        identity_number=d.get("identity_number"), status=d.get("status", "active"),
        hire_date=_pdate(d.get("hire_date")), birth_date=_pdate(d.get("birth_date")),
    )
    db.session.add(e)
    db.session.commit()
    return jsonify(employee=e.to_dict()), 201


@admin_bp.put("/employees/<int:eid>")
@jwt_required()
@MANAGE_HR
def employees_update(eid):
    e = db.session.get(Employee, eid)
    if not e:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and e.venue_id != forced:
        return _err("Bukan karyawan venue Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    for f in ("name", "position", "bank_account", "bank_name", "phone", "email", "identity_number", "status"):
        if f in d:
            setattr(e, f, d[f])
    if "salary" in d:
        e.salary = _promo(d["salary"])
    if "kasbon_installment" in d:
        e.kasbon_installment = _promo(d["kasbon_installment"])
    if "allowance" in d:
        e.allowance = _promo(d["allowance"])
    if "hire_date" in d:
        e.hire_date = _pdate(d["hire_date"])
    if "birth_date" in d:
        e.birth_date = _pdate(d["birth_date"])
    if forced is None and "venue_id" in d and d["venue_id"] and int(d["venue_id"]) != e.venue_id:
        if not _venue_or_404(d["venue_id"]):
            return _err("Venue tidak ditemukan", "not_found", 404)
        e.venue_id = d["venue_id"]
        # akun login (kalau ada) dibuat dgn venue_id disalin dr karyawan saat itu —
        # tak pernah disinkron otomatis lagi, jadi ikutkan di sini spy tak mismatch
        acc = _emp_account(eid)
        if acc:
            acc.venue_id = d["venue_id"]
    e.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(employee=e.to_dict()), 200


@admin_bp.delete("/employees/<int:eid>")
@jwt_required()
@MANAGE_HR
def employees_delete(eid):
    e = db.session.get(Employee, eid)
    if not e:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and e.venue_id != forced:
        return _err("Bukan karyawan venue Anda", "forbidden", 403)
    if _emp_account(e.id):
        return _err("Karyawan punya akun login — putuskan akun dulu.", "has_account", 409)
    db.session.delete(e)
    db.session.commit()
    return jsonify(message="Karyawan dihapus"), 200


@admin_bp.get("/employees/<int:eid>")
@jwt_required()
@VIEW
def employee_detail(eid):
    e = db.session.get(Employee, eid)
    if not e:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and e.venue_id != forced:
        return _err("Bukan karyawan venue Anda", "forbidden", 403)
    debts = (
        EmployeeDebt.query.filter_by(employee_id=eid)
        .order_by(EmployeeDebt.created_at.desc()).all()
    )
    acc = _emp_account(eid)
    d = e.to_dict()
    d["debt_balance"] = _emp_debt_balance(eid)
    d["debts"] = [x.to_dict() for x in debts]
    d["account"] = {"username": acc.username, "role": acc.role} if acc else None
    return jsonify(employee=d), 200


@admin_bp.post("/employees/<int:eid>/debt")
@jwt_required()
@MANAGE_HR
def employee_debt_add(eid):
    e = db.session.get(Employee, eid)
    if not e:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and e.venue_id != forced:
        return _err("Bukan karyawan venue Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    if d.get("type") not in ("advance", "repayment"):
        return _err("type harus advance|repayment")
    amt = _D(d.get("amount"))
    if amt <= 0:
        return _err("Jumlah harus > 0")
    db.session.add(EmployeeDebt(
        employee_id=eid, type=d["type"], amount=amt, note=d.get("note"),
        created_by=_current_user().id,
    ))
    db.session.commit()
    return jsonify(debt_balance=_emp_debt_balance(eid)), 201


# ------------------------------------------------------------------
# Papan Jadwal Layar Venue — tautan rahasia (display_token) utk TV di venue.
# ------------------------------------------------------------------
BOARD_BASE_URL = "https://jadwal.aspsports.id/layar.html"


def _board_link_or_403(vid):
    v = db.session.get(Venue, vid)
    if not v:
        return None, _err("Venue tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and vid not in vids:
        return None, _err("Bukan venue Anda", "forbidden", 403)
    return v, None


@admin_bp.get("/venues/<int:vid>/board-link")
@jwt_required()
@VIEW
def venue_board_link(vid):
    """Ambil tautan papan jadwal layar venue (buat token bila belum ada)."""
    v, err = _board_link_or_403(vid)
    if err:
        return err
    if not v.display_token:
        v.display_token = secrets.token_urlsafe(16)
        db.session.commit()
    return jsonify(url=f"{BOARD_BASE_URL}?token={v.display_token}"), 200


@admin_bp.post("/venues/<int:vid>/board-link/regenerate")
@jwt_required()
@VIEW
def venue_board_link_regen(vid):
    """Ganti token (tautan lama langsung mati) — mis. kalau bocor."""
    v, err = _board_link_or_403(vid)
    if err:
        return err
    v.display_token = secrets.token_urlsafe(16)
    db.session.commit()
    return jsonify(url=f"{BOARD_BASE_URL}?token={v.display_token}"), 200


# ------------------------------------------------------------------
# Pengajuan Kasbon (tab di menu Karyawan) — ajukan → HO setujui → otomatis
# catat advance + set cicilan di karyawan. Payroll potong otomatis (mekanisme lama).
# ------------------------------------------------------------------
KASBON_APPROVE = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE)


def _kasbon_scope_q():
    q = KasbonRequest.query
    vids = _scope_vids(_current_user())
    if vids is not None:
        q = q.filter(KasbonRequest.venue_id.in_(vids)) if vids else q.filter(db.false())
    return q


@admin_bp.get("/kasbon-requests")
@jwt_required()
@MANAGE_HR
def kasbon_requests_list():
    q = _kasbon_scope_q()
    if request.args.get("status"):
        q = q.filter_by(status=request.args.get("status"))
    if _scope_vids(_current_user()) is None and request.args.get("venue_id", type=int):
        q = q.filter_by(venue_id=request.args.get("venue_id", type=int))
    reqs = q.order_by(KasbonRequest.created_at.desc()).all()
    emps = {e.id: e.name for e in Employee.query.all()}
    vmap = {v.id: v.code for v in Venue.query.all()}
    out = []
    for r in reqs:
        d = r.to_dict(emps.get(r.employee_id), vmap.get(r.venue_id))
        # sisa kasbon = saldo hutang karyawan SAAT INI (berkurang otomatis via payroll)
        d["debt_balance"] = _emp_debt_balance(r.employee_id)
        out.append(d)
    return jsonify(count=len(out), requests=out), 200


@admin_bp.get("/kasbon-requests/pending-count")
@jwt_required()
@MANAGE_HR
def kasbon_pending_count():
    return jsonify(count=_kasbon_scope_q().filter_by(status="submitted").count()), 200


@admin_bp.post("/kasbon-requests")
@jwt_required()
@MANAGE_HR
def kasbon_request_create():
    d = request.get_json(silent=True) or {}
    emp = db.session.get(Employee, d.get("employee_id"))
    if not emp:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and emp.venue_id != forced:
        return _err("Bukan karyawan venue Anda", "forbidden", 403)
    amount = _D(d.get("amount"))
    months = int(d.get("months") or 0)
    if amount <= 0:
        return _err("Jumlah kasbon harus > 0")
    if months < 1:
        return _err("Jumlah bulan cicilan minimal 1")
    installment = float(math.ceil(amount / months))  # cicilan otomatis; sisa akhir ditangani payroll
    r = KasbonRequest(
        employee_id=emp.id, venue_id=emp.venue_id, amount=amount, months=months,
        installment=installment, note=d.get("note"), status="submitted",
        created_by=_current_user().id,
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(request=r.to_dict(emp.name)), 201


@admin_bp.post("/kasbon-requests/<int:rid>/approve")
@jwt_required()
@KASBON_APPROVE
def kasbon_request_approve(rid):
    r = db.session.get(KasbonRequest, rid)
    if not r:
        return _err("Pengajuan tidak ditemukan", "not_found", 404)
    if r.status != "submitted":
        return _err(f"Status '{r.status}' tak bisa disetujui", "bad_status", 409)
    emp = db.session.get(Employee, r.employee_id)
    if not emp:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    # OTOMATIS tulis ke data karyawan: saldo kasbon naik + cicilan ter-set
    db.session.add(EmployeeDebt(
        employee_id=emp.id, type="advance", amount=r.amount,
        note=f"Kasbon disetujui (cicil {r.months} bln)", created_by=_current_user().id,
    ))
    emp.kasbon_installment = r.installment
    emp.updated_at = datetime.utcnow()
    r.status = "approved"
    r.approved_by = _current_user().id
    r.approved_at = datetime.utcnow()
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(request=r.to_dict(emp.name)), 200


@admin_bp.post("/kasbon-requests/<int:rid>/reject")
@jwt_required()
@KASBON_APPROVE
def kasbon_request_reject(rid):
    r = db.session.get(KasbonRequest, rid)
    if not r:
        return _err("Pengajuan tidak ditemukan", "not_found", 404)
    if r.status != "submitted":
        return _err(f"Status '{r.status}' tak bisa ditolak", "bad_status", 409)
    d = request.get_json(silent=True) or {}
    r.status = "rejected"
    r.rejection_reason = d.get("reason")
    r.approved_by = _current_user().id
    r.approved_at = datetime.utcnow()
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(request=r.to_dict()), 200


@admin_bp.delete("/kasbon-requests/<int:rid>")
@jwt_required()
@MANAGE_HR
def kasbon_request_delete(rid):
    r = db.session.get(KasbonRequest, rid)
    if not r:
        return _err("Tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and r.venue_id != forced:
        return _err("Bukan venue Anda", "forbidden", 403)
    if r.status == "approved":
        return _err("Sudah disetujui — tak bisa dihapus", "locked", 409)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True), 200


@admin_bp.post("/employees/<int:eid>/account")
@jwt_required()
@MANAGE_HR
def employee_account_create(eid):
    """Buatkan akun login untuk karyawan (kasir=PIN, manager/admin=password)."""
    e = db.session.get(Employee, eid)
    if not e:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and e.venue_id != forced:
        return _err("Bukan karyawan venue Anda", "forbidden", 403)
    if _emp_account(eid):
        return _err("Karyawan sudah punya akun", "duplicate", 409)
    d = request.get_json(silent=True) or {}
    username = (d.get("username") or "").strip()
    role = d.get("role", "staff")
    if not username:
        return _err("username wajib diisi")
    if role not in ("staff", "staff_other", "manager_unit", "admin_unit", "head_office", "admin"):
        return _err("role tidak valid")
    # admin_unit = scope area → wajib pilih area
    area_id = None
    if role == "admin_unit":
        area_id = d.get("area_id")
        if not area_id or not db.session.get(Area, int(area_id)):
            return _err("Admin Unit wajib dipilihkan area yang valid")
    if User.query.filter_by(username=username).first():
        return _err("Username sudah dipakai", "duplicate", 409)
    email = e.email or f"{username}@aspsports.id"
    if User.query.filter_by(email=email).first():
        email = f"{username}.{eid}@aspsports.id"
    u = User(username=username, email=email, role=role, active=True,
             venue_id=e.venue_id, area_id=area_id, employee_id=e.id)
    pin, pw = d.get("pin"), d.get("password")
    if role in ("staff", "staff_other"):
        if not pin or len(str(pin)) < 4:
            return _err("PIN minimal 4 digit")
        u.pin_hash = hash_password(str(pin))
        u.set_password(str(pin))
    else:
        if not pw or len(str(pw)) < 8:
            return _err("Password minimal 8 karakter")
        u.set_password(str(pw))
        if pin:
            u.pin_hash = hash_password(str(pin))
    db.session.add(u)
    db.session.commit()
    return jsonify(account={"username": u.username, "role": u.role}), 201


@admin_bp.post("/employees/<int:eid>/account/reset")
@jwt_required()
@MANAGE_HR
def employee_account_reset(eid):
    """Ganti PIN (akun kasir) / password (akun lain) untuk karyawan yang sudah punya akun."""
    e = db.session.get(Employee, eid)
    if not e:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and e.venue_id != forced:
        return _err("Bukan karyawan venue Anda", "forbidden", 403)
    u = _emp_account(eid)
    if not u:
        return _err("Karyawan belum punya akun", "no_account", 404)
    d = request.get_json(silent=True) or {}
    if u.role in ("staff", "staff_other"):
        pin = str(d.get("pin") or "")
        if len(pin) < 4:
            return _err("PIN minimal 4 digit")
        u.pin_hash = hash_password(pin)
        u.set_password(pin)
        msg = "PIN diperbarui"
    else:
        # password & PIN independen — bisa isi salah satu atau dua-duanya
        # (mis. Manager yang juga perlu PIN POS, tanpa wajib ganti password)
        pw, pin = d.get("password"), d.get("pin")
        if not pw and not pin:
            return _err("Isi password atau PIN baru")
        msgs = []
        if pw:
            if len(str(pw)) < 8:
                return _err("Password minimal 8 karakter")
            u.set_password(str(pw))
            msgs.append("Password diperbarui")
        if pin:
            if len(str(pin)) < 4:
                return _err("PIN minimal 4 digit")
            u.pin_hash = hash_password(str(pin))
            msgs.append("PIN diperbarui")
        msg = " & ".join(msgs)
    db.session.commit()
    return jsonify(message=msg, account={"username": u.username, "role": u.role}), 200


@admin_bp.delete("/employees/<int:eid>/account")
@jwt_required()
@MANAGE_HR
def employee_account_delete(eid):
    """Putuskan akun login dari karyawan (supaya karyawan bisa dihapus).
    Hapus penuh bila akun tak punya riwayat; kalau ada riwayat → nonaktifkan & lepas."""
    from sqlalchemy.exc import IntegrityError

    e = db.session.get(Employee, eid)
    if not e:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and e.venue_id != forced:
        return _err("Bukan karyawan venue Anda", "forbidden", 403)
    u = _emp_account(eid)
    if not u:
        return _err("Karyawan belum punya akun", "no_account", 404)
    try:
        db.session.delete(u)
        db.session.flush()
        db.session.commit()
        return jsonify(message="Akun dihapus"), 200
    except IntegrityError:
        db.session.rollback()
        u = _emp_account(eid)
        u.active = False
        u.employee_id = None
        u.username = f"{u.username}__off{u.id}"  # bebaskan username utk dipakai lagi
        db.session.commit()
        return jsonify(message="Akun punya riwayat transaksi → dinonaktifkan & diputuskan"), 200


# ==================================================================
# PROMOS
# ==================================================================
def _pdate(s):
    try:
        return date.fromisoformat(s) if s else None
    except (TypeError, ValueError):
        return None


@admin_bp.get("/promos")
@jwt_required()
@VIEW
def promos_list():
    vid = request.args.get("venue_id", type=int)
    vids = _scope_vids(_current_user())
    q = db.session.query(Promo, Product).join(Product, Promo.product_id == Product.id)
    if vid:
        if vids is not None and vid not in vids:
            return _err("Venue di luar cakupan Anda", "forbidden", 403)
        q = q.filter(Product.venue_id == vid)
    elif vids is not None:
        q = q.filter(Product.venue_id.in_(vids)) if vids else q.filter(db.false())
    q = q.order_by(Promo.id.desc())
    rows = []
    for promo, prod in q.all():
        d = promo.to_dict()
        d["product_name"] = prod.name
        d["venue_id"] = prod.venue_id
        rows.append(d)
    return jsonify(count=len(rows), promos=rows), 200


def _promo_from_data(promo, d):
    promo.name = d.get("name") or promo.name
    promo.type = d.get("type", promo.type or "price")
    promo.promo_price = _promo(d.get("promo_price"))
    promo.percent = _promo(d.get("percent"))
    promo.buy_qty = int(d["buy_qty"]) if d.get("buy_qty") else None
    promo.get_qty = int(d["get_qty"]) if d.get("get_qty") else None
    promo.start_date = _pdate(d.get("start_date"))
    promo.end_date = _pdate(d.get("end_date"))
    if "is_active" in d:
        promo.is_active = bool(d["is_active"])


@admin_bp.post("/promos")
@jwt_required()
@PROMO_MANAGE
def promos_create():
    d = request.get_json(silent=True) or {}
    if not d.get("name") or not d.get("product_id"):
        return _err("name & product_id wajib diisi")
    prod = db.session.get(Product, d["product_id"])
    if not prod:
        return _err("Produk tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and prod.venue_id not in vids:
        return _err("Produk di luar cakupan Anda", "forbidden", 403)
    t = d.get("type", "price")
    if t not in ("price", "percent", "bogo"):
        return _err("type harus price|percent|bogo")
    if t == "price" and not d.get("promo_price"):
        return _err("Harga promo wajib untuk tipe price")
    if t == "percent" and not d.get("percent"):
        return _err("Persen wajib untuk tipe percent")
    if t == "bogo" and (not d.get("buy_qty") or not d.get("get_qty")):
        return _err("buy_qty & get_qty wajib untuk tipe bogo")
    promo = Promo(product_id=d["product_id"], is_active=True)
    _promo_from_data(promo, d)
    db.session.add(promo)
    db.session.commit()
    return jsonify(promo=promo.to_dict()), 201


@admin_bp.put("/promos/<int:pid>")
@jwt_required()
@PROMO_MANAGE
def promos_update(pid):
    promo = db.session.get(Promo, pid)
    if not promo:
        return _err("Promo tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None:
        prod = db.session.get(Product, promo.product_id)
        if not prod or prod.venue_id not in vids:
            return _err("Bukan promo produk cakupan Anda", "forbidden", 403)
    _promo_from_data(promo, request.get_json(silent=True) or {})
    db.session.commit()
    return jsonify(promo=promo.to_dict()), 200


@admin_bp.delete("/promos/<int:pid>")
@jwt_required()
@PROMO_MANAGE
def promos_delete(pid):
    promo = db.session.get(Promo, pid)
    if not promo:
        return _err("Promo tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None:
        prod = db.session.get(Product, promo.product_id)
        if not prod or prod.venue_id not in vids:
            return _err("Bukan promo produk cakupan Anda", "forbidden", 403)
    db.session.delete(promo)
    db.session.commit()
    return jsonify(message="Promo dihapus"), 200


# ==================================================================
# FACILITIES (lapangan)
# ==================================================================
@admin_bp.get("/facilities")
@jwt_required()
@VIEW
def facilities_list():
    q = Facility.query
    vid = request.args.get("venue_id", type=int)
    vids = _scope_vids(_current_user())
    if vid:
        if vids is not None and vid not in vids:
            return _err("Venue di luar cakupan Anda", "forbidden", 403)
        q = q.filter_by(venue_id=vid)
    elif vids is not None:
        q = q.filter(Facility.venue_id.in_(vids)) if vids else q.filter(db.false())
    items = q.order_by(Facility.venue_id, Facility.name).all()
    return jsonify(count=len(items), facilities=[f.to_dict() for f in items]), 200


def _parse_time(s, default):
    try:
        return datetime.strptime(s, "%H:%M").time()
    except (TypeError, ValueError):
        return default


@admin_bp.post("/facilities")
@jwt_required()
@FACILITY_MANAGE
def facilities_create():
    d = request.get_json(silent=True) or {}
    for f in ("name", "venue_id"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    if not _venue_or_404(d["venue_id"]):
        return _err("Venue tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and int(d["venue_id"]) not in vids:
        return _err("Venue di luar cakupan Anda", "forbidden", 403)
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
@FACILITY_MANAGE
def facilities_update(fid):
    fac = db.session.get(Facility, fid)
    if not fac:
        return _err("Lapangan tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and fac.venue_id not in vids:
        return _err("Bukan lapangan venue cakupan Anda", "forbidden", 403)
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


@admin_bp.delete("/facilities/<int:fid>")
@jwt_required()
@FACILITY_MANAGE
def facilities_delete(fid):
    fac = db.session.get(Facility, fid)
    if not fac:
        return _err("Lapangan tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and fac.venue_id not in vids:
        return _err("Bukan lapangan venue cakupan Anda", "forbidden", 403)
    # jangan hapus kalau sudah ada riwayat booking → sarankan nonaktifkan
    if FacilityBooking.query.filter_by(facility_id=fid).first():
        return _err(
            "Lapangan sudah punya riwayat booking — nonaktifkan saja (Edit → Nonaktif), jangan dihapus.",
            "has_bookings", 409,
        )
    db.session.delete(fac)  # rate_rules ikut terhapus (cascade)
    db.session.commit()
    return jsonify(ok=True), 200


# ------------------------------------------------------------------
# Tarif per rentang jam (facility_rate_rules) — 1 lapangan bisa punya
# harga beda2 tergantung jam (mis. malam lebih mahal dari siang).
# ------------------------------------------------------------------
def _facility_or_403(fid, u):
    fac = db.session.get(Facility, fid)
    if not fac:
        return None, _err("Lapangan tidak ditemukan", "not_found", 404)
    vids = _scope_vids(u)
    if vids is not None and fac.venue_id not in vids:
        return None, _err("Bukan lapangan venue cakupan Anda", "forbidden", 403)
    return fac, None


@admin_bp.get("/facilities/<int:fid>/rate-rules")
@jwt_required()
@VIEW
def facility_rate_rules_list(fid):
    fac, err = _facility_or_403(fid, _current_user())
    if err:
        return err
    return jsonify(count=len(fac.rate_rules), rate_rules=[r.to_dict() for r in fac.rate_rules]), 200


@admin_bp.post("/facilities/<int:fid>/rate-rules")
@jwt_required()
@FACILITY_MANAGE
def facility_rate_rules_create(fid):
    fac, err = _facility_or_403(fid, _current_user())
    if err:
        return err
    d = request.get_json(silent=True) or {}
    for f in ("start_time", "end_time", "hourly_rate"):
        if d.get(f) in (None, ""):
            return _err(f"{f} wajib diisi")
    start_t = _parse_time(d["start_time"], None)
    end_t = _parse_time(d["end_time"], None)
    if not start_t or not end_t:
        return _err("Format jam salah (HH:MM)")
    day_type = (d.get("day_type") or "weekday").strip()
    if day_type not in DAY_TYPES:
        return _err(f"Hari tidak valid. Pilihan: {', '.join(DAY_TYPES)}")
    rule = FacilityRateRule(
        facility_id=fid, label=(d.get("label") or "")[:50] or None, day_type=day_type,
        start_time=start_t, end_time=end_t, hourly_rate=_D(d["hourly_rate"]),
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(rate_rule=rule.to_dict()), 201


@admin_bp.put("/rate-rules/<int:rid>")
@jwt_required()
@FACILITY_MANAGE
def facility_rate_rule_update(rid):
    rule = db.session.get(FacilityRateRule, rid)
    if not rule:
        return _err("Aturan tarif tidak ditemukan", "not_found", 404)
    fac, err = _facility_or_403(rule.facility_id, _current_user())
    if err:
        return err
    d = request.get_json(silent=True) or {}
    if "label" in d:
        rule.label = (d.get("label") or "")[:50] or None
    if "day_type" in d:
        dt = (d.get("day_type") or "weekday").strip()
        if dt not in DAY_TYPES:
            return _err(f"Hari tidak valid. Pilihan: {', '.join(DAY_TYPES)}")
        rule.day_type = dt
    if "start_time" in d:
        t = _parse_time(d["start_time"], None)
        if not t:
            return _err("Format jam mulai salah (HH:MM)")
        rule.start_time = t
    if "end_time" in d:
        t = _parse_time(d["end_time"], None)
        if not t:
            return _err("Format jam selesai salah (HH:MM)")
        rule.end_time = t
    if "hourly_rate" in d:
        rule.hourly_rate = _D(d["hourly_rate"])
    db.session.commit()
    return jsonify(rate_rule=rule.to_dict()), 200


@admin_bp.delete("/rate-rules/<int:rid>")
@jwt_required()
@FACILITY_MANAGE
def facility_rate_rule_delete(rid):
    rule = db.session.get(FacilityRateRule, rid)
    if not rule:
        return _err("Aturan tarif tidak ditemukan", "not_found", 404)
    fac, err = _facility_or_403(rule.facility_id, _current_user())
    if err:
        return err
    db.session.delete(rule)
    db.session.commit()
    return jsonify(message="Aturan tarif dihapus"), 200


# ==================================================================
# COACHING (padel) — master coach & tarif per venue
# ==================================================================
def _venue_in_scope(vid, user):
    """None kalau boleh, atau response error kalau venue di luar cakupan user."""
    vids = _scope_vids(user)
    if vids is not None and int(vid) not in vids:
        return _err("Venue di luar cakupan Anda", "forbidden", 403)
    return None


@admin_bp.get("/coaches")
@jwt_required()
@VIEW
def coaches_list():
    q = Coach.query
    vid = request.args.get("venue_id", type=int)
    vids = _scope_vids(_current_user())
    if vid:
        err = _venue_in_scope(vid, _current_user())
        if err:
            return err
        q = q.filter_by(venue_id=vid)
    elif vids is not None:
        q = q.filter(Coach.venue_id.in_(vids)) if vids else q.filter(db.false())
    items = q.order_by(Coach.venue_id, Coach.name).all()
    # coach lama belum punya token — dibuatkan sekarang supaya tautannya siap
    if any(not c.schedule_token for c in items):
        for c in items:
            c.ensure_token()
        db.session.commit()

    # Kalau diberi slot (date/start_time/end_time), tiap coach ditandai:
    #   available = belum mengajar di jam itu (bentrok)
    #   declared  = coach menyatakan dirinya bisa
    # Dipakai dialog Reschedule utk memilih coach pengganti. exclude_booking_id
    # = slot yg sedang diedit, biar tak dianggap bentrok dgn dirinya sendiri.
    from ..pos.models import coach_declared_available
    from ..pos.services import is_coach_available

    d_str = request.args.get("date")
    s_str = request.args.get("start_time")
    e_str = request.args.get("end_time")
    exclude_id = request.args.get("exclude_booking_id", type=int)
    bdate = start = end = None
    if d_str and s_str and e_str:
        try:
            bdate = date.fromisoformat(d_str)
            start = datetime.strptime(s_str, "%H:%M").time()
            end = datetime.strptime(e_str, "%H:%M").time()
        except (ValueError, TypeError):
            bdate = start = end = None

    out = []
    for c in items:
        row = c.to_dict(with_token=True)
        if bdate:
            row["available"] = is_coach_available(c.id, bdate, start, end, exclude_id=exclude_id)
            row["declared"] = coach_declared_available(c.id, bdate, start, end)
        out.append(row)
    return jsonify(count=len(out), coaches=out), 200


@admin_bp.post("/coaches/<int:cid>/reset-token")
@jwt_required()
@FACILITY_MANAGE
def coaches_reset_token(cid):
    """Ganti tautan jadwal coach — dipakai kalau tautan lama bocor.
    Tautan lama langsung tak berlaku."""
    import secrets

    c = db.session.get(Coach, cid)
    if not c:
        return _err("Coach tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(c.venue_id, _current_user())
    if err:
        return err
    c.schedule_token = secrets.token_urlsafe(24)
    db.session.commit()
    return jsonify(coach=c.to_dict(with_token=True)), 200


@admin_bp.post("/coaches")
@jwt_required()
@FACILITY_MANAGE
def coaches_create():
    d = request.get_json(silent=True) or {}
    for f in ("name", "venue_id"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    if not _venue_or_404(d["venue_id"]):
        return _err("Venue tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(d["venue_id"], _current_user())
    if err:
        return err
    c = Coach(
        venue_id=d["venue_id"], name=d["name"][:100],
        phone=(d.get("phone") or None), is_active=bool(d.get("is_active", True)),
    )
    c.ensure_token()  # tautan jadwal pribadi langsung siap
    db.session.add(c)
    db.session.commit()
    return jsonify(coach=c.to_dict(with_token=True)), 201


@admin_bp.put("/coaches/<int:cid>")
@jwt_required()
@FACILITY_MANAGE
def coaches_update(cid):
    c = db.session.get(Coach, cid)
    if not c:
        return _err("Coach tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(c.venue_id, _current_user())
    if err:
        return err
    d = request.get_json(silent=True) or {}
    if d.get("name"):
        c.name = d["name"][:100]
    if "phone" in d:
        c.phone = d.get("phone") or None
    if "is_active" in d:
        c.is_active = bool(d["is_active"])
    db.session.commit()
    return jsonify(coach=c.to_dict(with_token=True)), 200


@admin_bp.delete("/coaches/<int:cid>")
@jwt_required()
@FACILITY_MANAGE
def coaches_delete(cid):
    """Hapus permanen hanya kalau coach belum pernah dipakai booking — kalau
    sudah, jejak siapa yg mengajar harus tetap ada; nonaktifkan saja."""
    c = db.session.get(Coach, cid)
    if not c:
        return _err("Coach tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(c.venue_id, _current_user())
    if err:
        return err
    used = FacilityBooking.query.filter_by(coach_id=cid).first()
    if used:
        return _err(
            "Coach ini sudah punya riwayat mengajar — tak bisa dihapus. "
            "Nonaktifkan saja supaya tak muncul lagi di POS.",
            "has_history", 409,
        )
    db.session.delete(c)
    db.session.commit()
    return jsonify(message="Coach dihapus"), 200


@admin_bp.get("/coach-availability")
@jwt_required()
@VIEW
def coach_availability_overview():
    """Ketersediaan semua coach dlm 1 tampilan (utk manajer): pola mingguan,
    tanggal khusus mendatang, kapan terakhir diperbarui, & sesi mendatang yg
    jatuh DI LUAR ketersediaan (termasuk yg dipaksakan kasir/override).

    Coach tanpa pola sama sekali = 'belum diatur' → dianggap selalu bisa;
    ditandai supaya manajer tahu siapa yg belum pernah mengisi."""
    from ..pos.models import CoachAvailability, CoachAvailabilityException
    from ..pos.services import coach_conflicting_sessions

    q = Coach.query.filter_by(is_active=True)
    vid = request.args.get("venue_id", type=int)
    vids = _scope_vids(_current_user())
    if vid:
        err = _venue_in_scope(vid, _current_user())
        if err:
            return err
        q = q.filter_by(venue_id=vid)
    elif vids is not None:
        q = q.filter(Coach.venue_id.in_(vids)) if vids else q.filter(db.false())

    today = date.today()
    out = []
    for c in q.order_by(Coach.name).all():
        pattern = {}
        for a in (
            CoachAvailability.query.filter_by(coach_id=c.id)
            .order_by(CoachAvailability.weekday, CoachAvailability.start_time)
            .all()
        ):
            pattern.setdefault(str(a.weekday), []).append(a.to_dict())
        excs = (
            CoachAvailabilityException.query.filter_by(coach_id=c.id)
            .filter(CoachAvailabilityException.date >= today)
            .order_by(CoachAvailabilityException.date)
            .all()
        )
        out.append({
            "coach_id": c.id, "coach_name": c.name, "phone": c.phone,
            "venue_id": c.venue_id,
            "configured": bool(pattern),
            "updated_at": c.availability_updated_at.isoformat() if c.availability_updated_at else None,
            "pattern": pattern,
            "exceptions": [e.to_dict() for e in excs],
            "conflicts": coach_conflicting_sessions(c.id),
        })
    return jsonify(count=len(out), coaches=out), 200


@admin_bp.get("/coaching-rate")
@jwt_required()
@VIEW
def coaching_rate_get():
    vid = request.args.get("venue_id", type=int)
    if not vid:
        return _err("venue_id wajib diisi")
    err = _venue_in_scope(vid, _current_user())
    if err:
        return err
    rate = db.session.get(CoachingRate, vid)
    return jsonify(rate=rate.to_dict() if rate else None), 200


@admin_bp.put("/coaching-rate")
@jwt_required()
@FACILITY_MANAGE
def coaching_rate_set():
    """Simpan/ubah tarif coaching venue (upsert). base_price = harga 1 peserta
    per jam; extra_person_price = tambahan tiap peserta berikutnya per jam."""
    d = request.get_json(silent=True) or {}
    vid = d.get("venue_id")
    if not vid:
        return _err("venue_id wajib diisi")
    if not _venue_or_404(vid):
        return _err("Venue tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(vid, _current_user())
    if err:
        return err
    try:
        max_p = int(d.get("max_persons") or 4)
    except (TypeError, ValueError):
        return _err("max_persons harus angka")
    if max_p < 1 or max_p > 20:
        return _err("max_persons harus 1–20")
    rate = db.session.get(CoachingRate, vid)
    if rate is None:
        rate = CoachingRate(venue_id=vid)
        db.session.add(rate)
    rate.base_price = _D(d.get("base_price"))
    rate.extra_person_price = _D(d.get("extra_person_price"))
    rate.max_persons = max_p
    rate.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(rate=rate.to_dict()), 200


# ==================================================================
# TERMINALS
# ==================================================================
@admin_bp.get("/terminals")
@jwt_required()
@VIEW
def terminals_list():
    q = PosTerminal.query
    vids = _scope_vids(_current_user())
    if vids is not None:
        q = q.filter(PosTerminal.venue_id.in_(vids)) if vids else q.filter(db.false())
    items = q.order_by(PosTerminal.venue_id, PosTerminal.code).all()
    return jsonify(terminals=[t.to_dict() for t in items]), 200


@admin_bp.post("/terminals")
@jwt_required()
@SETUP_MANAGE
def terminals_create():
    d = request.get_json(silent=True) or {}
    for f in ("code", "name", "venue_id"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    vids = _scope_vids(_current_user())
    if vids is not None and int(d["venue_id"]) not in vids:
        return _err("Venue di luar cakupan Anda", "forbidden", 403)
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
@SETUP_MANAGE
def cashiers_list():
    q = User.query.filter_by(role="staff")
    vids = _scope_vids(_current_user())
    if vids is not None:
        # cakupan terbatas tak boleh lihat kasir "semua venue" (venue_id NULL) milik role lain
        q = q.filter(User.venue_id.in_(vids)) if vids else q.filter(db.false())
    users = q.order_by(User.username).all()
    return jsonify(cashiers=[u.to_dict() for u in users]), 200


@admin_bp.post("/cashiers")
@jwt_required()
@SETUP_MANAGE
def cashiers_create():
    d = request.get_json(silent=True) or {}
    for f in ("username", "email", "pin"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    vids = _scope_vids(_current_user())
    if vids is not None:
        # scope terbatas: wajib pilih venue (tak boleh bikin kasir "semua venue"), & venue itu harus di cakupannya
        if not d.get("venue_id") or int(d["venue_id"]) not in vids:
            return _err("Venue di luar cakupan Anda (atau belum dipilih)", "forbidden", 403)
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
@SETUP_MANAGE
def cashiers_set_pin(uid):
    u = db.session.get(User, uid)
    if not u:
        return _err("User tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and u.venue_id not in vids:
        return _err("Kasir di luar cakupan Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    if len(str(d.get("pin", ""))) < 4:
        return _err("PIN minimal 4 digit")
    u.pin_hash = hash_password(str(d["pin"]))
    db.session.commit()
    return jsonify(message="PIN diperbarui"), 200


@admin_bp.put("/terminals/<int:tid>")
@jwt_required()
@SETUP_MANAGE
def terminals_update(tid):
    t = db.session.get(PosTerminal, tid)
    if not t:
        return _err("Terminal tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and t.venue_id not in vids:
        return _err("Terminal di luar cakupan Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    if "code" in d and d["code"] and d["code"] != t.code:
        if PosTerminal.query.filter_by(code=d["code"]).first():
            return _err("Kode terminal sudah dipakai", "duplicate", 409)
        t.code = d["code"]
    if "name" in d and d["name"]:
        t.name = d["name"]
    if "venue_id" in d and d["venue_id"]:
        if vids is not None and int(d["venue_id"]) not in vids:
            return _err("Venue di luar cakupan Anda", "forbidden", 403)
        t.venue_id = d["venue_id"]
    if "is_active" in d:
        t.is_active = bool(d["is_active"])
    db.session.commit()
    return jsonify(terminal=t.to_dict()), 200


@admin_bp.delete("/terminals/<int:tid>")
@jwt_required()
@SETUP_MANAGE
def terminals_delete(tid):
    t = db.session.get(PosTerminal, tid)
    if not t:
        return _err("Terminal tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and t.venue_id not in vids:
        return _err("Terminal di luar cakupan Anda", "forbidden", 403)
    n = Shift.query.filter_by(terminal_id=tid).count() + Order.query.filter_by(terminal_id=tid).count()
    if n:
        return _err(
            f"Terminal punya {n} transaksi/shift terkait. Nonaktifkan saja (jangan hapus).",
            "has_dependencies", 409,
        )
    db.session.delete(t)
    db.session.commit()
    return jsonify(message="Terminal dihapus"), 200


@admin_bp.put("/cashiers/<int:uid>")
@jwt_required()
@SETUP_MANAGE
def cashiers_update(uid):
    u = db.session.get(User, uid)
    if not u or u.role != "staff":
        return _err("Kasir tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and u.venue_id not in vids:
        return _err("Kasir di luar cakupan Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    if "username" in d and d["username"] and d["username"] != u.username:
        if User.query.filter_by(username=d["username"]).first():
            return _err("Username sudah dipakai", "duplicate", 409)
        u.username = d["username"]
    if "email" in d and d["email"] and d["email"] != u.email:
        if User.query.filter_by(email=d["email"]).first():
            return _err("Email sudah dipakai", "duplicate", 409)
        u.email = d["email"]
    if "venue_id" in d:
        new_vid = d["venue_id"] or None
        if vids is not None and (new_vid is None or int(new_vid) not in vids):
            return _err("Venue di luar cakupan Anda (atau tak boleh kosongkan)", "forbidden", 403)
        u.venue_id = new_vid
    if "active" in d:
        u.active = bool(d["active"])
    db.session.commit()
    return jsonify(cashier=u.to_dict()), 200


@admin_bp.delete("/cashiers/<int:uid>")
@jwt_required()
@SETUP_MANAGE
def cashiers_delete(uid):
    u = db.session.get(User, uid)
    if not u or u.role != "staff":
        return _err("Kasir tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and u.venue_id not in vids:
        return _err("Kasir di luar cakupan Anda", "forbidden", 403)
    n = Shift.query.filter_by(cashier_id=uid).count() + Order.query.filter_by(cashier_id=uid).count()
    if n:
        return _err(
            f"Kasir punya {n} transaksi/shift terkait. Nonaktifkan saja (jangan hapus).",
            "has_dependencies", 409,
        )
    db.session.delete(u)
    db.session.commit()
    return jsonify(message="Kasir dihapus"), 200


# ==================================================================
# ABSENSI (rekap kehadiran) — dari absen PIN di terminal POS
# ==================================================================
@admin_bp.get("/attendance")
@jwt_required()
@VIEW
def attendance_list():
    from datetime import timedelta

    today = (datetime.utcnow() + timedelta(hours=8)).date()  # WITA
    d_from = request.args.get("from") or today.isoformat()
    d_to = request.args.get("to") or today.isoformat()
    vid = request.args.get("venue_id", type=int)

    # scope: manager→venue-nya; admin_unit→area-nya; lainnya ikut ?venue_id
    u = _current_user()
    if u and u.role == ROLE_MANAGER:
        vid = u.venue_id
    scope_vids = None
    if u and u.role == "admin_unit":
        scope_vids = [v.id for v in Venue.query.filter_by(area_id=u.area_id).all()] if u.area_id else []

    q = Attendance.query.filter(Attendance.date.between(d_from, d_to))
    if vid:
        q = q.filter(Attendance.venue_id == vid)
    elif scope_vids is not None:
        q = q.filter(Attendance.venue_id.in_(scope_vids)) if scope_vids else q.filter(db.false())
    rows = q.order_by(Attendance.date.desc(), Attendance.check_in).all()

    # resolusi nama: employee.name kalau ada, else username
    emp_ids = {r.employee_id for r in rows if r.employee_id}
    uids = {r.user_id for r in rows if r.user_id}
    emps = {e.id: e.name for e in Employee.query.filter(Employee.id.in_(emp_ids)).all()} if emp_ids else {}
    users = {x.id: x.username for x in User.query.filter(User.id.in_(uids)).all()} if uids else {}
    vmap = {v.id: v.code for v in Venue.query.all()}

    out = []
    for r in rows:
        nm = emps.get(r.employee_id) or users.get(r.user_id) or "—"
        d = r.to_dict(name=nm)
        d["venue_code"] = vmap.get(r.venue_id)
        out.append(d)
    return jsonify(range={"from": d_from, "to": d_to}, count=len(out), attendance=out), 200


def _att_scope():
    """(vid, scope_vids) sesuai role: manager→venue-nya, admin_unit→area,
    lainnya ikut ?venue_id. scope_vids None = tak dibatasi area."""
    u = _current_user()
    vid = request.args.get("venue_id", type=int)
    if u and u.role == ROLE_MANAGER:
        return u.venue_id, None
    if u and u.role == "admin_unit":
        return vid, ([v.id for v in Venue.query.filter_by(area_id=u.area_id).all()] if u.area_id else [])
    return vid, None


@admin_bp.get("/attendance/roster")
@jwt_required()
@VIEW
def attendance_roster():
    """Roster kehadiran 1 hari: SEMUA karyawan aktif per venue + statusnya
    (dihitung live, tak perlu bikin baris kosong). Status: hadir / belum absen
    (hari ini) / alpha (hari lewat, tak hadir tanpa keterangan) / izin/sakit/cuti."""
    from datetime import timedelta

    today = (datetime.utcnow() + timedelta(hours=8)).date()
    the_date = request.args.get("date") or today.isoformat()
    try:
        d = date.fromisoformat(the_date)
    except ValueError:
        return _err("Format tanggal salah", "bad_request")
    is_today = d >= today

    vid, scope_vids = _att_scope()
    empq = Employee.query.filter(Employee.status == "active")
    if vid:
        empq = empq.filter(Employee.venue_id == vid)
    elif scope_vids is not None:
        empq = empq.filter(Employee.venue_id.in_(scope_vids)) if scope_vids else empq.filter(db.false())
    employees = empq.order_by(Employee.name).all()
    emp_ids = [e.id for e in employees]

    atts = {
        a.employee_id: a
        for a in Attendance.query.filter(Attendance.date == d, Attendance.employee_id.in_(emp_ids)).all()
    } if emp_ids else {}
    vmap = {v.id: v.code for v in Venue.query.all()}

    def status_of(a):
        if a and a.status:
            return a.status  # izin | sakit | cuti | off
        if a and a.check_in:
            return "hadir"
        return "belum" if is_today else "alpha"

    rows, summary = [], {"hadir": 0, "belum": 0, "alpha": 0, "izin": 0, "sakit": 0, "cuti": 0, "off": 0}
    for e in employees:
        a = atts.get(e.id)
        st = status_of(a)
        summary[st] = summary.get(st, 0) + 1
        base = {
            "employee_id": e.id, "name": e.name, "position": e.position,
            "venue_id": e.venue_id, "venue_code": vmap.get(e.venue_id),
            "att_status": st, "attendance_id": a.id if a else None,
            "check_in": None, "check_out": None, "check_out_date": None,
            "out_next_day": False, "work_hours": None, "status": None,
            "has_in_photo": False, "has_out_photo": False,
            "check_in_address": None, "check_out_address": None,
        }
        if a:
            base.update(a.to_dict(name=e.name))
            base["att_status"] = st
            base["attendance_id"] = a.id
        rows.append(base)
    return jsonify(date=the_date, count=len(rows), summary=summary, rows=rows), 200


@admin_bp.post("/attendance/leave")
@jwt_required()
@MANAGE_HR
def attendance_set_leave():
    """Tandai karyawan izin/sakit/cuti pada 1 tanggal (atau 'clear' utk batal).
    Manajer hanya utk venue-nya. Cuti panjang = tandai per hari (keputusan user)."""
    d = request.get_json(silent=True) or {}
    emp = db.session.get(Employee, d.get("employee_id"))
    if not emp:
        return _err("Karyawan tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and emp.venue_id not in vids:
        return _err("Karyawan di luar cakupan venue Anda", "forbidden", 403)
    status = (d.get("status") or "").strip()
    if status not in ("izin", "sakit", "cuti", "off", "clear"):
        return _err("status harus izin/sakit/cuti/off/clear", "bad_request")
    try:
        the_date = date.fromisoformat(d.get("date"))
    except (ValueError, TypeError):
        return _err("Tanggal tidak valid", "bad_request")

    row = Attendance.query.filter_by(employee_id=emp.id, date=the_date).first()
    if row is None:
        if status == "clear":
            return jsonify(message="Tidak ada yang diubah"), 200
        acc = User.query.filter_by(employee_id=emp.id).first()
        row = Attendance(user_id=acc.id if acc else None, employee_id=emp.id,
                         venue_id=emp.venue_id, date=the_date)
        db.session.add(row)
    if status == "clear":
        # baris murni keterangan (tanpa absen) → hapus; kalau ada absen, cukup lepas status
        if not row.check_in and not row.check_out:
            db.session.delete(row)
        else:
            row.status = None
    else:
        row.status = status
    db.session.commit()
    return jsonify(message="Tersimpan"), 200


@admin_bp.get("/attendance/leave-report")
@jwt_required()
@VIEW
def attendance_leave_report():
    """Rekap izin/sakit/cuti per periode, per karyawan (jumlah hari tiap jenis)."""
    today = (datetime.utcnow() + timedelta(hours=8)).date()
    d_from = request.args.get("from") or today.replace(day=1).isoformat()
    d_to = request.args.get("to") or today.isoformat()
    vid, scope_vids = _att_scope()

    q = Attendance.query.filter(
        Attendance.date.between(d_from, d_to),
        Attendance.status.in_(["izin", "sakit", "cuti", "off"]),
    )
    if vid:
        q = q.filter(Attendance.venue_id == vid)
    elif scope_vids is not None:
        q = q.filter(Attendance.venue_id.in_(scope_vids)) if scope_vids else q.filter(db.false())
    recs = q.order_by(Attendance.date.desc()).all()

    emp_ids = {r.employee_id for r in recs if r.employee_id}
    emps = {e.id: e for e in Employee.query.filter(Employee.id.in_(emp_ids)).all()} if emp_ids else {}
    vmap = {v.id: v.code for v in Venue.query.all()}

    per_emp, detail = {}, []
    for r in recs:
        e = emps.get(r.employee_id)
        nm = e.name if e else "—"
        pe = per_emp.setdefault(r.employee_id, {
            "employee_id": r.employee_id, "name": nm,
            "venue_code": vmap.get(r.venue_id), "izin": 0, "sakit": 0, "cuti": 0, "off": 0,
        })
        pe[r.status] = pe.get(r.status, 0) + 1
        detail.append({
            "date": r.date.isoformat(), "name": nm, "venue_code": vmap.get(r.venue_id),
            "status": r.status,
        })
    total = {"izin": 0, "sakit": 0, "cuti": 0, "off": 0}
    for pe in per_emp.values():
        for k in total:
            total[k] += pe[k]
    return jsonify(
        range={"from": d_from, "to": d_to},
        per_employee=sorted(per_emp.values(), key=lambda x: x["name"]),
        detail=detail, total=total,
    ), 200


@admin_bp.get("/attendance/<int:aid>/photo/<which>")
@jwt_required()
@VIEW
def attendance_photo(aid, which):
    import os
    from flask import current_app, send_file

    a = db.session.get(Attendance, aid)
    if not a or which not in ("in", "out"):
        return _err("Tidak ditemukan", "not_found", 404)
    fn = a.check_in_photo if which == "in" else a.check_out_photo
    if not fn:
        return _err("Tidak ada foto", "not_found", 404)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], "attendance", fn)
    if not os.path.exists(path):
        return _err("File tidak ada", "not_found", 404)
    return send_file(path, mimetype="image/jpeg")


@admin_bp.get("/payments/<int:pid>/proof")
@jwt_required()
@VIEW
def payment_proof(pid):
    import os
    from flask import current_app, send_file

    p = db.session.get(Payment, pid)
    if not p or not p.proof_image:
        return _err("Tidak ada bukti transfer", "not_found", 404)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], "payment_proof", p.proof_image)
    if not os.path.exists(path):
        return _err("File tidak ada", "not_found", 404)
    return send_file(path, mimetype="image/jpeg")


@admin_bp.delete("/attendance/<int:aid>")
@jwt_required()
@MANAGE_HR
def attendance_delete(aid):
    """Hapus baris absensi keliru (mis. salah venue/kembar) — hanya rekap,
    tak ada efek kas/payroll yang perlu dibalik."""
    import os

    from flask import current_app

    a = db.session.get(Attendance, aid)
    if not a:
        return _err("Absensi tidak ditemukan", "not_found", 404)
    u = _current_user()
    if u and u.role == ROLE_MANAGER and a.venue_id != u.venue_id:
        return _err("Bukan absensi venue Anda", "forbidden", 403)
    if u and u.role == "admin_unit":
        vids = [v.id for v in Venue.query.filter_by(area_id=u.area_id).all()] if u.area_id else []
        if a.venue_id not in vids:
            return _err("Bukan absensi area Anda", "forbidden", 403)
    for fn in (a.check_in_photo, a.check_out_photo):
        if fn:
            path = os.path.join(current_app.config["UPLOAD_FOLDER"], "attendance", fn)
            if os.path.exists(path):
                os.remove(path)
    db.session.delete(a)
    db.session.commit()
    return jsonify(message="Absensi dihapus"), 200


# ==================================================================
# DASHBOARD
# ==================================================================
# Tipe venue yang dianggap venue bisnis (utk Sales Growth MoM); Manajemen &
# Premium Sport sengaja tidak dimasukkan.
TRACKED_VENUE_TYPES = {"Waterpark", "Mini Soccer", "Lapangan Bola", "Futsal", "Padel", "esport"}


def _sales_growth_mom(vids):
    today = date.today()
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    days_in_last_month = calendar.monthrange(last_month_start.year, last_month_start.month)[1]
    last_month_compare_end = last_month_start.replace(day=min(today.day, days_in_last_month))

    venues_q = Venue.query.filter(Venue.type.in_(TRACKED_VENUE_TYPES))
    if vids is not None:
        venues_q = venues_q.filter(Venue.id.in_(vids)) if vids else venues_q.filter(db.false())
    venues = venues_q.order_by(Venue.type, Venue.name).all()

    def _revenue_by_venue(d_from, d_to):
        rows = (
            db.session.query(Order.venue_id, func.coalesce(func.sum(Payment.amount), 0))
            .join(Payment, Payment.order_id == Order.id)
            .filter(Payment.status == "paid", func.date(Payment.paid_at).between(d_from, d_to))
            .group_by(Order.venue_id)
            .all()
        )
        return {vid: float(amt) for vid, amt in rows}

    this_rev = _revenue_by_venue(this_month_start, today)
    last_rev = _revenue_by_venue(last_month_start, last_month_compare_end)

    result = []
    for v in venues:
        this_m = this_rev.get(v.id, 0.0)
        last_m = last_rev.get(v.id, 0.0)
        growth_pct = None
        is_new = False
        if last_m > 0:
            growth_pct = round((this_m - last_m) / last_m * 100, 1)
        elif this_m > 0:
            is_new = True
        result.append({
            "venue_id": v.id,
            "venue_name": v.name,
            "venue_type": v.type,
            "this_month": round(this_m, 2),
            "last_month": round(last_m, 2),
            "growth_pct": growth_pct,
            "is_new": is_new,
        })

    return {
        "this_month_range": {"from": this_month_start.isoformat(), "to": today.isoformat()},
        "last_month_range": {"from": last_month_start.isoformat(), "to": last_month_compare_end.isoformat()},
        "venues": result,
    }


@admin_bp.get("/dashboard/summary")
@jwt_required()
def dashboard_summary():
    u = _current_user()
    vids = _scope_vids(u)  # None = semua venue (admin/head_office)

    def _scoped(q, model):
        if vids is None:
            return q
        if not vids:
            return q.filter(db.false())
        return q.filter(model.venue_id.in_(vids))

    today = date.today()
    yesterday = today - timedelta(days=1)

    pay_today_q = _scoped(
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.status == "paid", func.date(Payment.paid_at) == today),
        Order,
    )
    pay_yesterday_q = _scoped(
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.status == "paid", func.date(Payment.paid_at) == yesterday),
        Order,
    )
    revenue_today = float(pay_today_q.scalar() or 0)
    revenue_yesterday = float(pay_yesterday_q.scalar() or 0)

    order_count_today = _scoped(
        Order.query.filter(Order.status == "paid", func.date(Order.created_at) == today),
        Order,
    ).count()

    ops_pending = _scoped(OpRequest.query.filter_by(status="submitted"), OpRequest).count()
    payroll_pending = _scoped(PayrollRun.query.filter_by(status="submitted"), PayrollRun).count()
    proc_pending = _scoped(PurchaseOrder.query.filter_by(status="submitted"), PurchaseOrder).count()

    low_stock_q = _scoped(
        Product.query.filter(
            Product.is_active.is_(True),
            Product.track_stock.is_(True),
            Product.stock_qty <= Product.min_stock,
        ),
        Product,
    )
    low_stock_count = low_stock_q.count()
    low_stock_items = [
        {"id": p.id, "name": p.name, "stock_qty": p.stock_qty, "min_stock": p.min_stock}
        for p in low_stock_q.order_by(Product.stock_qty).limit(8).all()
    ]

    return jsonify(
        date=today.isoformat(),
        revenue_today=round(revenue_today, 2),
        revenue_yesterday=round(revenue_yesterday, 2),
        order_count_today=order_count_today,
        approvals_pending={
            "ops": ops_pending,
            "payroll": payroll_pending,
            "procurement": proc_pending,
            "total": ops_pending + payroll_pending + proc_pending,
        },
        low_stock={"count": low_stock_count, "items": low_stock_items},
        sales_growth_mom=_sales_growth_mom(vids),
    ), 200


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
@REPORT_SALES
def report_sales():
    d_from, d_to = _date_range()
    # cakupan venue: manajer -> venue-nya; admin_unit -> venue area-nya; admin/HO
    # -> semua atau 1 venue yg dipilih.
    ids = _report_scope()

    # --- basis kas: pembayaran yang DITERIMA dalam rentang (DP + pelunasan) ---
    pay_q = (
        db.session.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.status == "paid")
        .filter(func.date(Payment.paid_at).between(d_from, d_to))
    )
    if ids is not None:
        pay_q = pay_q.filter(Order.venue_id.in_(ids)) if ids else pay_q.filter(db.false())

    total_received = float(
        pay_q.with_entities(func.coalesce(func.sum(Payment.amount), 0)).scalar() or 0
    )
    payment_count = pay_q.count()

    by_method = [
        {"method": m, "amount": float(a)}
        for m, a in pay_q.with_entities(
            Payment.method, func.coalesce(func.sum(Payment.amount), 0)
        ).group_by(Payment.method).all()
    ]
    daily = [
        {"date": str(day), "revenue": float(a)}
        for day, a in pay_q.with_entities(
            func.date(Payment.paid_at), func.coalesce(func.sum(Payment.amount), 0)
        ).group_by(func.date(Payment.paid_at)).order_by(func.date(Payment.paid_at)).all()
    ]

    # --- komposisi jenis: dari order LUNAS dibuat dalam rentang ---
    ord_q = Order.query.filter(
        Order.status == "paid", func.date(Order.created_at).between(d_from, d_to)
    )
    if ids is not None:
        ord_q = ord_q.filter(Order.venue_id.in_(ids)) if ids else ord_q.filter(db.false())
    paid_ids = [o.id for o in ord_q.with_entities(Order.id).all()]
    by_type = []
    consignment = {"own_revenue": 0.0, "consignment_revenue": 0.0, "consignment_owed": 0.0}
    if paid_ids:
        by_type = [
            {"item_type": t, "amount": float(a)}
            for t, a in db.session.query(
                OrderItem.item_type, func.coalesce(func.sum(OrderItem.line_total), 0)
            ).filter(OrderItem.order_id.in_(paid_ids)).group_by(OrderItem.item_type).all()
        ]

        # --- breakdown konsinyasi vs milik venue sendiri ---
        rows = (
            db.session.query(
                Product.is_consignment,
                func.coalesce(func.sum(OrderItem.line_total), 0),
                func.coalesce(func.sum(OrderItem.quantity * func.coalesce(Product.consignment_price, 0)), 0),
            )
            .select_from(OrderItem)
            .outerjoin(Product, OrderItem.product_id == Product.id)
            .filter(OrderItem.order_id.in_(paid_ids))
            .group_by(Product.is_consignment)
            .all()
        )
        for is_cons, revenue, owed in rows:
            if is_cons:
                consignment["consignment_revenue"] += float(revenue)
                consignment["consignment_owed"] += float(owed)
            else:
                consignment["own_revenue"] += float(revenue)
        consignment["consignment_margin"] = round(
            consignment["consignment_revenue"] - consignment["consignment_owed"], 2
        )
        for k in ("own_revenue", "consignment_revenue", "consignment_owed"):
            consignment[k] = round(consignment[k], 2)

    return jsonify(
        range={"from": d_from, "to": d_to},
        total_revenue=total_received,
        order_count=payment_count,
        consignment=consignment,
        by_method=by_method,
        by_item_type=by_type,
        daily=daily,
    ), 200


@admin_bp.get("/reports/shifts")
@jwt_required()
@REPORT_SALES
def report_shifts():
    d_from, d_to = _date_range()
    ids = _report_scope()  # manajer->venue; admin_unit->area; admin/HO->semua/1
    # Muncul kalau shift DIBUKA atau DITUTUP dalam rentang (shift yg dibiarkan
    # terbuka lintas hari tetap terlihat di tanggal tutupnya).
    q = Shift.query.filter(db.or_(
        func.date(Shift.opened_at).between(d_from, d_to),
        func.date(Shift.closed_at).between(d_from, d_to),
    ))
    if ids is not None:
        q = q.filter(Shift.venue_id.in_(ids)) if ids else q.filter(db.false())
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


# ------------------------------------------------------------------
# Radar Operasional (Fase 1 — deterministik, TANPA AI)
# ------------------------------------------------------------------
# Menyapu data harian → tandai kejanggalan → urut per bobot rupiah. Framing
# "perlu dicek", BUKAN tuduhan. Semua dari data yg ada (tanpa tabel/migrasi baru).
# Ambang batas sengaja konstanta di sini supaya gampang dituning tanpa bongkar logika.
RADAR_VARIANCE_MIN = 50_000       # |selisih kas| >= ini baru ditandai (buang recehan)
RADAR_RECUR_DAYS = 7              # jendela deteksi pola selisih berulang
RADAR_RECUR_COUNT = 2            # kasir sama selisih >= sekian kali dlm jendela = pola
RADAR_DEPOSIT_STALE_DAYS = 1     # shift closed belum disetor > sekian hari = perlu dicek


def _rp(n):
    return "Rp " + f"{int(round(abs(n))):,}".replace(",", ".")


def _radar_findings(vids):
    """vids: None = semua venue (admin/HO); list = dibatasi (manager → venue-nya).
    Kembalikan daftar temuan deterministik, sudah diberi `severity` (bobot rupiah)
    untuk diurut. Tak menyentuh AI sama sekali."""
    from collections import defaultdict

    now = datetime.utcnow()
    findings = []
    vcode = {v.id: v.code for v in Venue.query.all()}
    uname = {u.id: u.username for u in User.query.all()}

    base = Shift.query.filter(Shift.status == "closed")
    if vids is not None:
        base = base.filter(Shift.venue_id.in_(vids)) if vids else base.filter(db.false())

    # ---------- Sinyal 1: Selisih Kas ----------
    var_shifts = [
        s for s in base.filter(Shift.cash_variance.isnot(None)).all()
        if s.cash_variance is not None and abs(float(s.cash_variance)) >= RADAR_VARIANCE_MIN
    ]
    # 1B — pola berulang per kasir dlm jendela (sinyal terpenting)
    recur_cut = now - timedelta(days=RADAR_RECUR_DAYS)
    per_cashier = defaultdict(list)
    for s in var_shifts:
        if s.closed_at and s.closed_at >= recur_cut:
            per_cashier[(s.cashier_id, s.venue_id)].append(s)
    grouped = set()
    for (cid, vid), slist in per_cashier.items():
        if len(slist) >= RADAR_RECUR_COUNT:
            total = sum(float(s.cash_variance) for s in slist)
            grouped.update(s.id for s in slist)
            findings.append({
                "signal": "cash_variance_recurring",
                "level": "high",
                "severity": abs(total),
                "venue_id": vid, "venue_code": vcode.get(vid),
                "title": f"Kasir {uname.get(cid, '?')} selisih kas {len(slist)}× dalam {RADAR_RECUR_DAYS} hari",
                "detail": f"Total selisih {_rp(total)} dari {len(slist)} shift. Pola berulang — perlu dicek.",
                "amount": total,
                "occurred_at": max(s.closed_at for s in slist).isoformat(),
                "link": {"view": "reports", "tab": "shifts", "venue_id": vid},
            })
    # 1A — selisih besar sekali jalan (yg belum masuk pola berulang)
    for s in var_shifts:
        if s.id in grouped:
            continue
        v = float(s.cash_variance)
        findings.append({
            "signal": "cash_variance_single",
            "level": "high" if abs(v) >= RADAR_VARIANCE_MIN * 4 else "medium",
            "severity": abs(v),
            "venue_id": s.venue_id, "venue_code": vcode.get(s.venue_id),
            "title": f"Selisih kas {_rp(v)} {'(kurang)' if v < 0 else '(lebih)'} — kasir {uname.get(s.cashier_id, '?')}",
            "detail": f"Shift {s.closed_at.date().isoformat() if s.closed_at else ''} uang fisik {'kurang' if v < 0 else 'lebih'} {_rp(v)} dari seharusnya.",
            "amount": v,
            "occurred_at": s.closed_at.isoformat() if s.closed_at else None,
            "link": {"view": "reports", "tab": "shifts", "venue_id": s.venue_id},
        })

    # ---------- Sinyal 2: Shift Belum Disetor ----------
    stale_cut = now - timedelta(days=RADAR_DEPOSIT_STALE_DAYS)
    undep = base.filter(
        Shift.deposit_id.is_(None),
        Shift.deposit_amount.isnot(None),
        Shift.deposit_amount > 0,
    ).all()
    per_venue = defaultdict(list)
    for s in undep:
        if s.closed_at and s.closed_at <= stale_cut:
            per_venue[s.venue_id].append(s)
    for vid, slist in per_venue.items():
        total = sum(float(s.deposit_amount or 0) for s in slist)
        oldest = min(s.closed_at for s in slist)
        age = (now - oldest).days
        findings.append({
            "signal": "undeposited_shift",
            "level": "high" if age >= 3 else "medium",
            "severity": total,
            "venue_id": vid, "venue_code": vcode.get(vid),
            "title": f"{len(slist)} shift belum disetor — {vcode.get(vid, '')}",
            "detail": f"Total {_rp(total)}, tertua {age} hari lalu. Segera setor / rekonsiliasi.",
            "amount": total,
            "occurred_at": oldest.isoformat(),
            "link": {"view": "treasury", "tab": "deposits", "venue_id": vid},
        })

    findings.sort(key=lambda f: f["severity"], reverse=True)
    return findings


@admin_bp.get("/radar")
@jwt_required()
@VIEW
def radar():
    """Radar Operasional — owner/admin/HO lihat semua venue; manager lihat
    venue-nya sendiri (scope sama dgn master data)."""
    vids = _scope_vids(_current_user())
    items = _radar_findings(vids)
    counts = {
        "high": sum(1 for f in items if f["level"] == "high"),
        "medium": sum(1 for f in items if f["level"] == "medium"),
        "total": len(items),
    }
    return jsonify(count=len(items), counts=counts, findings=items), 200


# Cache briefing di memori: key = tanda-tangan temuan (scope+isi), value = teks.
# Karena briefing cuma berubah kalau temuannya berubah, ini mencegah panggilan AI
# berulang tiap buka Dashboard (hemat biaya). Per-worker; reset saat restart — aman.
_BRIEFING_CACHE = {}

BRIEFING_SYSTEM = (
    "Kamu asisten yang meringkas 'Radar Operasional' untuk pemilik bisnis venue olahraga "
    "yang mengelola belasan cabang dari jauh. Tulis SATU paragraf singkat (2-4 kalimat) dalam "
    "Bahasa Indonesia yang natural, menyapa langsung ('Pagi ini...'), menyorot 1-2 hal paling "
    "penting (rupiah terbesar/paling berisiko) dan sisanya diringkas. Framing 'perlu dicek', "
    "BUKAN tuduhan mencuri. Jangan pakai poin/bullet, jangan mengulang semua angka mentah, "
    "jangan mengarang data di luar yang diberikan. Ajak bertindak singkat di akhir."
)


def _briefing_signature(vids, findings):
    scope = "all" if vids is None else ",".join(map(str, sorted(vids)))
    body = ";".join(f"{f['signal']}:{f['venue_id']}:{round(f['severity'])}" for f in findings)
    return scope + "|" + body


@admin_bp.get("/radar/briefing")
@jwt_required()
@VIEW
def radar_briefing():
    """Briefing AI (1 paragraf) atas temuan radar. Di-cache per tanda-tangan temuan
    supaya tak memanggil AI tiap buka Dashboard. Tanpa temuan → tak panggil AI."""
    from ..ai.service import AIError, AINotConfigured, ai_complete

    vids = _scope_vids(_current_user())
    findings = _radar_findings(vids)
    if not findings:
        return jsonify(briefing=None, empty=True), 200

    sig = _briefing_signature(vids, findings)
    if sig in _BRIEFING_CACHE:
        return jsonify(briefing=_BRIEFING_CACHE[sig], cached=True), 200

    payload = "\n".join(f"- [{f['level']}] {f['title']} — {f['detail']}" for f in findings)
    try:
        text = ai_complete(
            BRIEFING_SYSTEM,
            [{"role": "user", "content": "Temuan radar hari ini:\n" + payload}],
            max_tokens=400,
        )
    except AINotConfigured:
        return jsonify(briefing=None, not_configured=True), 200
    except AIError:
        return jsonify(briefing=None, error=True), 200

    text = text.strip()
    _BRIEFING_CACHE[sig] = text
    # jaga cache tak membengkak (temuan berubah-ubah tiap hari)
    if len(_BRIEFING_CACHE) > 50:
        _BRIEFING_CACHE.pop(next(iter(_BRIEFING_CACHE)))
    return jsonify(briefing=text, cached=False), 200


@admin_bp.delete("/shifts/<int:shift_id>")
@jwt_required()
@ORDER_CANCEL
def shift_delete(shift_id):
    """Hapus shift — HANYA yang sudah ditutup & TANPA transaksi (tak ada order
    dibuat, tak ada pembayaran masuk, tak ada gerakan kas). Utk membersihkan
    shift kosong/uji. Shift yang ada transaksi TAK BOLEH dihapus (jejak keuangan)."""
    from ..pos.models import CashMovement, Order, Payment

    shift = db.session.get(Shift, shift_id)
    if not shift:
        return _err("Shift tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(shift.venue_id, _current_user())
    if err:
        return err
    if shift.status != "closed":
        return _err("Shift masih terbuka — tutup dulu sebelum bisa dihapus.", "shift_open", 409)
    n_ord = Order.query.filter_by(shift_id=shift_id).count()
    n_pay = Payment.query.filter_by(shift_id=shift_id).count()
    n_cm = CashMovement.query.filter_by(shift_id=shift_id).count()
    if n_ord or n_pay or n_cm:
        return _err(
            f"Shift punya transaksi ({n_ord} order, {n_pay} pembayaran, {n_cm} kas) — "
            "tak bisa dihapus. Batalkan/koreksi transaksinya dulu.",
            "has_transactions", 409,
        )
    db.session.delete(shift)
    db.session.commit()
    return jsonify(message="Shift dihapus"), 200


@admin_bp.post("/shifts/<int:shift_id>/reopen")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, ROLE_ADMIN_UNIT)
def shift_reopen(shift_id):
    """Buka kembali shift yang sudah ditutup untuk koreksi. Admin/HO: semua
    venue; manajer: venue-nya. Setelah dibuka: status → open, transaksi bisa
    ditambah/dibatalkan/diubah (total ikut menyesuaikan), lalu TUTUP LAGI
    (expected_cash & selisih dihitung ulang). Wajib alasan; dicatat di audit.
    Ditolak kalau kas shift sudah DISETOR (tarik setoran dulu)."""
    shift = db.session.get(Shift, shift_id)
    if not shift:
        return _err("Shift tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(shift.venue_id, _current_user())
    if err:
        return err
    if shift.status != "closed":
        return _err("Shift belum ditutup — tak perlu dibuka.", "not_closed", 409)
    if shift.deposit_id is not None:
        return _err(
            "Kas shift ini sudah DISETOR — tarik/batalkan setoran dulu sebelum "
            "membuka kembali, supaya kas bank tidak kacau.",
            "already_deposited", 409,
        )
    d = request.get_json(silent=True) or {}
    reason = (d.get("reason") or "").strip()
    if not reason:
        return _err("Alasan buka kembali wajib diisi.")
    # snapshot kondisi kas sebelum dibuka (utk audit)
    db.session.add(ShiftReopenLog(
        shift_id=shift.id, venue_id=shift.venue_id, reason=reason,
        variance_before=shift.cash_variance, counted_before=shift.counted_cash,
        deposit_before=shift.deposit_amount, reopened_by=_current_user().id,
    ))
    # kembalikan ke status buka; kunci-kunci penutupan direset (akan dihitung
    # ulang saat ditutup lagi). Total penjualan DIBIARKAN — akan menyesuaikan
    # sendiri saat ada transaksi ditamb/dibatalkan.
    shift.status = "open"
    shift.closed_at = None
    shift.counted_cash = None
    shift.cash_variance = None
    shift.expected_cash = 0
    shift.deposit_amount = None
    shift.reopened_count = (shift.reopened_count or 0) + 1
    db.session.commit()
    return jsonify(message="Shift dibuka kembali — silakan koreksi lalu tutup lagi.", shift=shift.to_dict()), 200


@admin_bp.post("/shifts/<int:shift_id>/close")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, ROLE_ADMIN_UNIT)
def shift_close_admin(shift_id):
    """Tutup shift dari back office (mis. setelah dibuka kembali & dikoreksi,
    tanpa lewat terminal kasir). Admin/HO: semua venue; manajer: venue-nya.
    expected_cash & selisih dihitung ulang otomatis oleh close_shift."""
    from ..pos.services import PosError, close_shift

    shift = db.session.get(Shift, shift_id)
    if not shift:
        return _err("Shift tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(shift.venue_id, _current_user())
    if err:
        return err
    if shift.status != "open":
        return _err("Shift tidak dalam keadaan terbuka.", "not_open", 409)
    d = request.get_json(silent=True) or {}
    if d.get("counted_cash") in (None, ""):
        return _err("Uang tunai dihitung (counted_cash) wajib diisi.")
    try:
        close_shift(
            shift, d.get("counted_cash"),
            deposit_amount=d.get("deposit_amount"),
            notes=d.get("notes"),
        )
    except PosError as e:
        return _err(e.message, e.code, e.status)
    return jsonify(message="Shift ditutup.", shift=shift.to_dict()), 200


@admin_bp.post("/shifts/<int:shift_id>/adjust")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE)
def shift_adjust(shift_id):
    """Penyesuaian shift CEPAT (+/- per metode) langsung dari tabel rekonsiliasi.
    Dibuat sbg order+payment back-date (tgl shift) supaya Laporan Shift &
    Laporan Penjualan tetap konsisten. Shift ditutup pun boleh (tak perlu buka
    dulu); expected_cash & selisih dihitung ulang. Ditolak jika sudah disetor."""
    shift = db.session.get(Shift, shift_id)
    if not shift:
        return _err("Shift tidak ditemukan", "not_found", 404)
    if shift.deposit_id is not None:
        return _err("Kas shift sudah DISETOR — tarik setoran dulu.", "already_deposited", 409)
    d = request.get_json(silent=True) or {}
    note = (d.get("note") or "").strip()
    if not note:
        return _err("Catatan/alasan penyesuaian wajib diisi.")
    deltas = {
        "cash": float(_D(d.get("cash"))),
        "qris": float(_D(d.get("qris"))),
        "transfer": float(_D(d.get("transfer"))),
    }
    if all(abs(v) < 0.005 for v in deltas.values()):
        return _err("Isi minimal satu nominal penyesuaian (boleh minus).")

    back_dt = shift.opened_at or datetime.utcnow()
    venue = db.session.get(Venue, shift.venue_id)
    prefix = f"{venue.code}-{back_dt:%Y%m%d}-"
    existing = db.session.query(Order.order_number).filter(Order.order_number.like(prefix + "%")).all()
    max_seq = 0
    for (num,) in existing:
        try:
            max_seq = max(max_seq, int(num.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    order_number = f"ADJ-{prefix}{max_seq + 1:04d}"[:30]
    net = sum(deltas.values())

    order = Order(
        order_number=order_number, venue_id=shift.venue_id, terminal_id=shift.terminal_id,
        shift_id=shift.id, cashier_id=shift.cashier_id, customer_name="[PENYESUAIAN]",
        status="paid", subtotal=net, discount_amount=0, total_amount=net, amount_paid=net,
        notes=f"Penyesuaian shift oleh {_current_user().username}: {note}",
        created_at=back_dt, updated_at=datetime.utcnow(),
    )
    order.items.append(OrderItem(
        item_type="product", name_snapshot=f"Penyesuaian shift: {note}"[:120],
        unit_price=net, quantity=1, line_total=net, created_at=back_dt,
    ))
    for method, amt in deltas.items():
        if abs(amt) < 0.005:
            continue
        order.payments.append(Payment(
            method=method, provider=method, amount=amt, status="paid",
            shift_id=shift.id, paid_at=back_dt, created_at=back_dt,
            confirmed_by=_current_user().id, reference=f"Penyesuaian: {note}"[:100],
        ))
    # terapkan ke akumulasi shift
    shift.total_cash_sales = float(shift.total_cash_sales or 0) + deltas["cash"]
    shift.total_qris_sales = float(shift.total_qris_sales or 0) + deltas["qris"]
    shift.total_transfer_sales = float(shift.total_transfer_sales or 0) + deltas["transfer"]
    shift.total_sales = float(shift.total_sales or 0) + net
    # hitung ulang expected & selisih (kalau sudah pernah dihitung)
    shift.expected_cash = (
        float(shift.opening_cash or 0) + float(shift.total_cash_sales or 0)
        + float(shift.cash_in or 0) - float(shift.cash_out or 0)
    )
    if shift.counted_cash is not None:
        shift.cash_variance = float(shift.counted_cash) - float(shift.expected_cash)
    db.session.add(order)
    db.session.add(ShiftAdjustLog(
        shift_id=shift.id, venue_id=shift.venue_id, cash_delta=deltas["cash"],
        qris_delta=deltas["qris"], transfer_delta=deltas["transfer"], note=note,
        order_number=order_number, adjusted_by=_current_user().id,
    ))
    db.session.commit()
    return jsonify(message="Penyesuaian shift tersimpan (konsisten dgn laporan penjualan).",
                   shift=shift.to_dict()), 201


@admin_bp.get("/shifts/<int:shift_id>/orders")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, ROLE_ADMIN_UNIT)
def shift_orders(shift_id):
    """Rincian transaksi yang sudah dientry pada 1 shift — utk dilihat & dikoreksi.
    Admin/HO: semua venue. Manajer: hanya venue-nya sendiri."""
    shift = db.session.get(Shift, shift_id)
    if not shift:
        return _err("Shift tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(shift.venue_id, _current_user())
    if err:
        return err
    orders = Order.query.filter_by(shift_id=shift_id).order_by(Order.created_at).all()
    ucache = {}

    def cashier_name(uid):
        if uid not in ucache:
            u = db.session.get(User, uid) if uid else None
            ucache[uid] = u.username if u else None
        return ucache[uid]

    out = []
    for o in orders:
        dd = o.to_dict()
        dd["cashier"] = cashier_name(o.cashier_id)
        out.append(dd)
    return jsonify(shift=shift.to_dict(), orders=out), 200


@admin_bp.post("/shifts/<int:shift_id>/opening-cash")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, ROLE_ADMIN_UNIT)
def shift_edit_opening_cash(shift_id):
    """Koreksi Saldo Awal (modal) shift — mis. salah input saat buka shift.
    Kas seharusnya & selisih dihitung ulang. Admin/HO: semua venue; manajer:
    venue-nya. Ditolak jika sudah disetor."""
    shift = db.session.get(Shift, shift_id)
    if not shift:
        return _err("Shift tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(shift.venue_id, _current_user())
    if err:
        return err
    if shift.deposit_id is not None:
        return _err("Kas shift sudah DISETOR — tak bisa ubah saldo awal.", "already_deposited", 409)
    d = request.get_json(silent=True) or {}
    if d.get("opening_cash") in (None, ""):
        return _err("Saldo awal wajib diisi.")
    new_open = float(_D(d.get("opening_cash")))
    if new_open < 0:
        return _err("Saldo awal tidak boleh negatif.")
    old_open = float(shift.opening_cash or 0)
    shift.opening_cash = new_open
    shift.expected_cash = (
        new_open + float(shift.total_cash_sales or 0)
        + float(shift.cash_in or 0) - float(shift.cash_out or 0)
    )
    if shift.counted_cash is not None:
        shift.cash_variance = float(shift.counted_cash) - float(shift.expected_cash)
    db.session.add(ShiftAdjustLog(
        shift_id=shift.id, venue_id=shift.venue_id, cash_delta=0, qris_delta=0, transfer_delta=0,
        note=f"Koreksi saldo awal: Rp {int(old_open):,} → Rp {int(new_open):,}".replace(",", "."),
        adjusted_by=_current_user().id,
    ))
    db.session.commit()
    return jsonify(message="Saldo awal dikoreksi.", shift=shift.to_dict()), 200


@admin_bp.put("/orders/<int:order_id>/edit-items")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, ROLE_ADMIN_UNIT)
def order_edit_items(order_id):
    """Koreksi item produk/tiket sebuah transaksi (nama/qty/harga) + rekonsiliasi:
    total order, pembayaran (paid terakhir disesuaikan), dan akumulasi shift —
    semuanya menyesuaikan otomatis, tanggal transaksi dipertahankan. Item
    booking/rental TAK diubah di sini (pakai reschedule/cancel).
    Admin/HO: semua venue. Manajer: hanya venue-nya. Stok TIDAK otomatis disesuaikan."""
    order = db.session.get(Order, order_id)
    if not order:
        return _err("Transaksi tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(order.venue_id, _current_user())
    if err:
        return err
    if order.status == "void":
        return _err("Transaksi sudah dibatalkan — tak bisa diedit.", "bad_status", 409)
    from ..pos.services import edit_order_items_core
    d = request.get_json(silent=True) or {}
    err = edit_order_items_core(order, d.get("items") or [])
    if err:
        return _err(err[0], err[1], 409)
    db.session.commit()
    return jsonify(message="Transaksi dikoreksi.", order=order.to_dict()), 200


@admin_bp.post("/shifts/<int:shift_id>/correction-entry")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, ROLE_ADMIN_UNIT)
def shift_correction_entry(shift_id):
    """Tambah transaksi KOREKSI back-date ke shift (yg sudah dibuka kembali).
    Berbeda dgn POS: tanggal (paid_at & created_at) DISAMAKAN ke tanggal shift,
    supaya Laporan Penjualan (basis paid_at) & Laporan Shift (basis opened_at)
    konsisten. Order langsung berstatus lunas & masuk akumulasi shift.
    Admin/HO semua venue; manajer/admin_unit sesuai cakupan."""
    shift = db.session.get(Shift, shift_id)
    if not shift:
        return _err("Shift tidak ditemukan", "not_found", 404)
    err = _venue_in_scope(shift.venue_id, _current_user())
    if err:
        return err
    if shift.status != "open":
        return _err("Shift harus dalam keadaan TERBUKA (buka kembali dulu).", "not_open", 409)
    d = request.get_json(silent=True) or {}
    method = (d.get("method") or "").strip()
    if method not in ("cash", "qris", "transfer"):
        return _err("Metode bayar wajib (cash/qris/transfer).")
    items = d.get("items") or []
    if not items:
        return _err("Minimal 1 baris item.")

    # tanggal koreksi = tanggal shift (back-date). Jam dibuat = jam buka shift.
    back_dt = shift.opened_at or datetime.utcnow()
    venue = db.session.get(Venue, shift.venue_id)

    # nomor order pakai prefix TANGGAL SHIFT (bukan hari ini)
    prefix = f"{venue.code}-{back_dt:%Y%m%d}-"
    existing = db.session.query(Order.order_number).filter(Order.order_number.like(prefix + "%")).all()
    max_seq = 0
    for (num,) in existing:
        try:
            max_seq = max(max_seq, int(num.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    order_number = f"{prefix}{max_seq + 1:04d}"

    total = 0.0
    parsed = []
    for it in items:
        name = (it.get("name") or "").strip()
        qty = _D(it.get("qty") or it.get("quantity"))
        price = _D(it.get("unit_price"))
        if not name or qty <= 0 or price < 0:
            return _err("Baris tidak valid (nama, qty > 0, harga >= 0).")
        line = float(qty) * float(price)
        total += line
        parsed.append((name, float(qty), float(price), line, it.get("product_id"), bool(it.get("deduct_stock"))))
    if total <= 0:
        return _err("Total koreksi harus > 0.")

    order = Order(
        order_number=order_number, venue_id=shift.venue_id, terminal_id=shift.terminal_id,
        shift_id=shift.id, cashier_id=shift.cashier_id, customer_name=d.get("customer_name"),
        status="paid", subtotal=total, discount_amount=0, total_amount=total, amount_paid=total,
        created_at=back_dt, updated_at=datetime.utcnow(),
    )
    for (name, qty, price, line, product_id, deduct) in parsed:
        order.items.append(OrderItem(
            item_type="product", product_id=product_id, name_snapshot=name,
            unit_price=price, quantity=qty, line_total=line, created_at=back_dt,
        ))
        # opsional kurangi stok (kalau produk tracked & diminta)
        if product_id and deduct:
            prod = db.session.get(Product, product_id)
            if prod and prod.track_stock:
                prod.stock_qty -= int(qty)
                db.session.add(StockMovement(
                    product_id=prod.id, venue_id=shift.venue_id, type="sale",
                    quantity=-int(qty), balance_after=prod.stock_qty,
                    reference=order_number, created_by=_current_user().id,
                ))
    order.payments.append(Payment(
        method=method, provider=method, amount=total, status="paid",
        shift_id=shift.id, paid_at=back_dt, created_at=back_dt,
        confirmed_by=_current_user().id,
        reference=f"Koreksi back-date oleh {_current_user().username}",
    ))
    # akumulasi shift
    shift.total_sales = float(shift.total_sales or 0) + total
    if method == "cash":
        shift.total_cash_sales = float(shift.total_cash_sales or 0) + total
    elif method == "qris":
        shift.total_qris_sales = float(shift.total_qris_sales or 0) + total
    elif method == "transfer":
        shift.total_transfer_sales = float(shift.total_transfer_sales or 0) + total
    db.session.add(order)
    db.session.commit()
    return jsonify(message="Transaksi koreksi ditambahkan (tanggal disamakan ke tanggal shift).",
                   order=order.to_dict()), 201


@admin_bp.get("/shifts/reopen-logs")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, ROLE_ADMIN_UNIT)
def shift_reopen_logs():
    """Jejak audit buka-kembali shift (tab riwayat). Manajer/admin_unit: venue
    cakupannya saja; admin/HO semua."""
    q = ShiftReopenLog.query
    vids = _scope_vids(_current_user())
    if vids is not None:
        q = q.filter(ShiftReopenLog.venue_id.in_(vids)) if vids else q.filter(db.false())
    elif request.args.get("venue_id", type=int):
        q = q.filter(ShiftReopenLog.venue_id == request.args.get("venue_id", type=int))
    rows = q.order_by(ShiftReopenLog.reopened_at.desc()).limit(500).all()
    emp_names = {e.id: e.name for e in Employee.query.all()}
    users = {u.id: (emp_names.get(u.employee_id) or u.username) for u in User.query.all()}
    return jsonify(logs=[r.to_dict(users) for r in rows]), 200


@admin_bp.get("/shifts/adjust-logs")
@jwt_required()
@roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE)
def shift_adjust_logs():
    """Jejak audit penyesuaian shift (+/- per metode)."""
    q = ShiftAdjustLog.query
    if request.args.get("venue_id", type=int):
        q = q.filter(ShiftAdjustLog.venue_id == request.args.get("venue_id", type=int))
    rows = q.order_by(ShiftAdjustLog.adjusted_at.desc()).limit(500).all()
    emp_names = {e.id: e.name for e in Employee.query.all()}
    users = {u.id: (emp_names.get(u.employee_id) or u.username) for u in User.query.all()}
    return jsonify(logs=[r.to_dict(users) for r in rows]), 200


# ======================================================================
# EVENT — kelola dari portal (manajer venue-nya, admin/HO semua). Fase 2.
# ======================================================================
EVENT_ROLES = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)


def _event_venue_id(body_or_arg):
    """venue_id efektif: manajer dipaksa ke venue-nya; admin/HO ambil dari input."""
    forced = _forced_venue()
    if forced is not None:
        return forced
    vid = body_or_arg
    return int(vid) if vid else None


def _parse_ev(d):
    df = datetime.strptime(d["date_from"], "%Y-%m-%d").date()
    dto = datetime.strptime(d["date_to"], "%Y-%m-%d").date()
    st = datetime.strptime(d["start_time"], "%H:%M").time()
    et = datetime.strptime(d["end_time"], "%H:%M").time()
    return df, dto, st, et


@admin_bp.get("/events/quote")
@jwt_required()
@EVENT_ROLES
def admin_event_quote():
    from ..pos.services import event_conflicts, event_price_quote

    vid = _event_venue_id(request.args.get("venue_id", type=int))
    if not vid:
        return _err("venue_id wajib")
    try:
        df, dto, st, et = _parse_ev(request.args)
    except (KeyError, ValueError):
        return _err("Tanggal/jam tidak lengkap/valid")
    if dto < df:
        return _err("Tanggal selesai sebelum tanggal mulai")
    price, n = event_price_quote(vid, df, dto, st, et)
    conflicts = event_conflicts(vid, df, dto, st, et)
    return jsonify(suggested_price=price, facility_count=n, conflict_count=len(conflicts)), 200


@admin_bp.get("/events")
@jwt_required()
@EVENT_ROLES
def admin_events_list():
    q = Event.query
    forced = _forced_venue()
    if forced is not None:
        q = q.filter(Event.venue_id == forced)
    elif request.args.get("venue_id", type=int):
        q = q.filter(Event.venue_id == request.args.get("venue_id", type=int))
    if request.args.get("scope") != "all":
        q = q.filter(Event.status == "active", Event.date_to >= date.today())
    events = q.order_by(Event.date_from.desc()).limit(300).all()
    # ringkasan bayar order + jumlah bentrok
    from ..pos.services import event_conflicts
    out = []
    for e in events:
        d = e.to_dict()
        order = db.session.get(Order, e.order_id) if e.order_id else None
        d["order_status"] = order.status if order else None
        d["amount_paid"] = float(order.amount_paid) if order else 0
        d["conflict_count"] = len(event_conflicts(
            e.venue_id, e.date_from, e.date_to, e.start_time, e.end_time,
            exclude_order_id=e.order_id)) if e.status == "active" else 0
        out.append(d)
    return jsonify(events=out), 200


@admin_bp.get("/events/<int:event_id>")
@jwt_required()
@EVENT_ROLES
def admin_event_detail(event_id):
    from ..pos.services import event_conflicts

    ev = db.session.get(Event, event_id)
    if not ev:
        return _err("Event tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and ev.venue_id != forced:
        return _err("Bukan event venue Anda", "forbidden", 403)
    conflicts = event_conflicts(ev.venue_id, ev.date_from, ev.date_to, ev.start_time, ev.end_time,
                                exclude_order_id=ev.order_id)
    contacted = {c.order_id for c in EventContact.query.filter_by(event_id=ev.id).all()}
    for c in conflicts:
        c["contacted"] = c["order_id"] in contacted
    order = db.session.get(Order, ev.order_id) if ev.order_id else None
    d = ev.to_dict()
    d["order_status"] = order.status if order else None
    d["amount_paid"] = float(order.amount_paid) if order else 0
    d["amount_due"] = float(order.total_amount - order.amount_paid) if order else 0
    return jsonify(event=d, conflicts=conflicts), 200


@admin_bp.post("/events")
@jwt_required()
@EVENT_ROLES
def admin_event_create():
    from ..pos.services import event_conflicts, generate_order_number

    d = request.get_json(silent=True) or {}
    vid = _event_venue_id(d.get("venue_id"))
    if not vid:
        return _err("venue_id wajib")
    venue = db.session.get(Venue, vid)
    if not venue:
        return _err("Venue tidak ditemukan", "not_found", 404)
    name = (d.get("name") or "").strip()
    if not name:
        return _err("Nama event wajib")
    try:
        df, dto, st, et = _parse_ev(d)
    except (KeyError, ValueError):
        return _err("Tanggal/jam tidak lengkap/valid")
    if dto < df:
        return _err("Tanggal selesai sebelum tanggal mulai")
    price = _D(d.get("price"))
    if price < 0:
        return _err("Harga tidak valid")

    uid = _current_user().id
    label = f"Sewa Event: {name} ({df.isoformat()}"
    label += f"–{dto.isoformat()}" if dto != df else ""
    label += f" {st.strftime('%H:%M')}-{et.strftime('%H:%M')})"
    # order UNPAID (dibayar nanti di POS/Pelunasan) — portal tak lewat shift/terminal
    order = Order(
        order_number=generate_order_number(venue), venue_id=vid, cashier_id=uid,
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
        venue_id=vid, name=name, renter=d.get("renter"), phone=d.get("phone"),
        date_from=df, date_to=dto, start_time=st, end_time=et, price=price,
        order_id=order.id, status="active", notes=d.get("notes"), created_by=uid,
    )
    db.session.add(ev)
    db.session.commit()
    conflicts = event_conflicts(vid, df, dto, st, et, exclude_order_id=order.id)
    return jsonify(event=ev.to_dict(), order=order.to_dict(), conflicts=conflicts), 201


@admin_bp.put("/events/<int:event_id>")
@jwt_required()
@EVENT_ROLES
def admin_event_update(event_id):
    ev = db.session.get(Event, event_id)
    if not ev:
        return _err("Event tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and ev.venue_id != forced:
        return _err("Bukan event venue Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    if "name" in d:
        ev.name = (d.get("name") or ev.name).strip()
    if "renter" in d:
        ev.renter = d.get("renter")
    if "phone" in d:
        ev.phone = d.get("phone")
    if "notes" in d:
        ev.notes = d.get("notes")
    try:
        if "date_from" in d:
            ev.date_from = datetime.strptime(d["date_from"], "%Y-%m-%d").date()
        if "date_to" in d:
            ev.date_to = datetime.strptime(d["date_to"], "%Y-%m-%d").date()
        if "start_time" in d:
            ev.start_time = datetime.strptime(d["start_time"], "%H:%M").time()
        if "end_time" in d:
            ev.end_time = datetime.strptime(d["end_time"], "%H:%M").time()
    except ValueError:
        return _err("Tanggal/jam tidak valid")
    if ev.date_to < ev.date_from:
        return _err("Tanggal selesai sebelum tanggal mulai")
    if "price" in d:
        ev.price = _D(d.get("price"))
        order = db.session.get(Order, ev.order_id) if ev.order_id else None
        if order and order.status in ("open", "partial"):
            order.subtotal = ev.price
            order.total_amount = ev.price
            for it in order.items:
                if it.item_type == "event":
                    it.unit_price = ev.price
                    it.line_total = ev.price
    db.session.commit()
    return jsonify(event=ev.to_dict()), 200


@admin_bp.post("/events/<int:event_id>/cancel")
@jwt_required()
@EVENT_ROLES
def admin_event_cancel(event_id):
    ev = db.session.get(Event, event_id)
    if not ev:
        return _err("Event tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and ev.venue_id != forced:
        return _err("Bukan event venue Anda", "forbidden", 403)
    ev.status = "cancelled"
    db.session.commit()
    return jsonify(message="Event dibatalkan (jadwal terbuka kembali).", event=ev.to_dict()), 200


@admin_bp.post("/events/<int:event_id>/contacted")
@jwt_required()
@EVENT_ROLES
def admin_event_contacted(event_id):
    ev = db.session.get(Event, event_id)
    if not ev:
        return _err("Event tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and ev.venue_id != forced:
        return _err("Bukan event venue Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    oid = d.get("order_id")
    if not oid:
        return _err("order_id wajib")
    existing = EventContact.query.filter_by(event_id=ev.id, order_id=int(oid)).first()
    if existing:  # toggle → batal tandai
        db.session.delete(existing)
        db.session.commit()
        return jsonify(contacted=False), 200
    db.session.add(EventContact(event_id=ev.id, order_id=int(oid), contacted_by=_current_user().id))
    db.session.commit()
    return jsonify(contacted=True), 200


@admin_bp.get("/bookings")
@jwt_required()
@VIEW
def bookings_list():
    """Daftar booking lapangan + info order (customer)."""
    from datetime import timedelta

    today = date.today()
    d_from = request.args.get("from") or today.isoformat()
    d_to = request.args.get("to") or (today + timedelta(days=90)).isoformat()
    forced = _forced_venue()
    vid = forced if forced is not None else request.args.get("venue_id", type=int)
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
    # filter coaching: coach_id tertentu, atau 'any' = semua yg pakai coach
    coach_arg = request.args.get("coach_id")
    if coach_arg == "any":
        q = q.filter(FacilityBooking.coach_id.isnot(None))
    elif coach_arg:
        try:
            q = q.filter(FacilityBooking.coach_id == int(coach_arg))
        except ValueError:
            pass
    q = q.order_by(FacilityBooking.booking_date, FacilityBooking.start_time)

    coach_names = {c.id: c.name for c in Coach.query.all()}

    rows = []
    for fb, fac, order in q.all():
        row = fb.to_dict()
        row["facility_name"] = fac.name
        row["coach_name"] = coach_names.get(fb.coach_id)
        row["venue_id"] = fb.venue_id
        row["order_item_id"] = fb.order_item_id
        row["order_id"] = order.id if order else None
        row["order_number"] = order.order_number if order else None
        row["customer_name"] = order.customer_name if order else None
        row["customer_phone"] = order.customer_phone if order else None
        if order:
            total = float(order.total_amount or 0)
            paid = float(order.amount_paid or 0)
            row["order_total"] = total
            row["order_paid"] = paid
            row["order_due"] = round(total - paid, 2)
            row["payment_status"] = order.status  # open|partial|paid|void
            # tanggal DP = pembayaran (paid) paling awal; tanggal pelunasan =
            # pembayaran paling akhir HANYA kalau order sudah lunas penuh
            paid_pays = sorted(
                [p for p in order.payments if p.status == "paid" and p.paid_at],
                key=lambda p: p.paid_at,
            )
            row["dp_at"] = paid_pays[0].paid_at.isoformat() if paid_pays else None
            row["paid_off_at"] = (
                paid_pays[-1].paid_at.isoformat() if (paid_pays and order.status == "paid") else None
            )
            # cara bayar: metode yg BENAR-BENAR sudah masuk, urut waktu bayar &
            # tanpa duplikat (DP cash lalu pelunasan QRIS → ["cash","qris"])
            methods = []
            for p in paid_pays:
                if p.method and p.method not in methods:
                    methods.append(p.method)
            row["payment_methods"] = methods
        else:
            row["order_total"] = row["order_paid"] = row["order_due"] = None
            row["payment_status"] = None
            row["dp_at"] = row["paid_off_at"] = None
            row["payment_methods"] = []
        rows.append(row)
    return jsonify(range={"from": d_from, "to": d_to}, count=len(rows), bookings=rows), 200


@admin_bp.get("/bookings/forfeited-dp")
@jwt_required()
@VIEW
def bookings_forfeited_dp():
    """DP Hangus: order booking yg BATAL (void) tapi DP-nya sudah dibayar &
    TIDAK direfund (payment tetap 'paid'). READ-ONLY — uangnya sudah tercatat
    di kas (ikut cash shift → setoran), ini cuma pelabelan per venue utk
    visibilitas, TIDAK menambah/mengurangi uang. Difilter per tanggal DP masuk
    (paid_at). Dikelompokkan per order (bukan per booking) supaya tak dobel."""
    today = date.today()
    d_from = request.args.get("from") or today.replace(day=1).isoformat()
    d_to = request.args.get("to") or today.isoformat()
    forced = _forced_venue()
    vid = forced if forced is not None else request.args.get("venue_id", type=int)

    q = Order.query.filter(Order.status == "void")
    if vid:
        q = q.filter(Order.venue_id == vid)

    venue_codes = {v.id: v.code for v in Venue.query.all()}
    rows, per_venue = [], {}
    for o in q.all():
        paid_pays = [
            p for p in o.payments
            if p.status == "paid" and p.paid_at and d_from <= p.paid_at.date().isoformat() <= d_to
        ]
        forfeited = round(sum(float(p.amount) for p in paid_pays), 2)
        if forfeited <= 0:
            continue
        dp_at = min(p.paid_at for p in paid_pays)
        item_ids = [i.id for i in o.items]
        bdates = sorted(
            fb.booking_date.isoformat()
            for fb in FacilityBooking.query.filter(FacilityBooking.order_item_id.in_(item_ids)).all()
        ) if item_ids else []
        rows.append({
            "order_id": o.id, "order_number": o.order_number, "venue_id": o.venue_id,
            "venue_code": venue_codes.get(o.venue_id, f"#{o.venue_id}"),
            "customer_name": o.customer_name, "customer_phone": o.customer_phone,
            "forfeited": forfeited, "dp_at": dp_at.isoformat(),
            "order_total": float(o.total_amount or 0), "booking_dates": bdates,
        })
        pv = per_venue.setdefault(o.venue_id, {
            "venue_id": o.venue_id, "venue_code": venue_codes.get(o.venue_id, f"#{o.venue_id}"),
            "count": 0, "total": 0.0,
        })
        pv["count"] += 1
        pv["total"] = round(pv["total"] + forfeited, 2)

    rows.sort(key=lambda r: r["dp_at"], reverse=True)
    return jsonify(
        rows=rows,
        per_venue=sorted(per_venue.values(), key=lambda x: -x["total"]),
        total=round(sum(r["forfeited"] for r in rows), 2),
        range={"from": d_from, "to": d_to},
    ), 200


@admin_bp.get("/reports/coaching")
@jwt_required()
@VIEW
def report_coaching():
    """Rekap coaching per coach: jam mengajar & nilai coaching per periode.

    Basis **TANGGAL MAIN** (booking_date), bukan tanggal bayar — karena yg
    ditanya "berapa jam coach mengajar di periode ini". Beda dgn laporan
    penjualan yg basis kas; ditegaskan di UI supaya tak dikira selisih.
    Sesi batal (booking cancelled / order void) tidak dihitung."""
    today = date.today()
    d_from = request.args.get("from") or today.replace(day=1).isoformat()
    d_to = request.args.get("to") or today.isoformat()
    forced = _forced_venue()
    vid = forced if forced is not None else request.args.get("venue_id", type=int)

    q = (
        db.session.query(FacilityBooking, Facility, Coach, OrderItem, Order)
        .join(Facility, FacilityBooking.facility_id == Facility.id)
        .join(Coach, FacilityBooking.coach_id == Coach.id)
        .outerjoin(OrderItem, FacilityBooking.coaching_item_id == OrderItem.id)
        .outerjoin(Order, OrderItem.order_id == Order.id)
        .filter(
            FacilityBooking.booking_date.between(d_from, d_to),
            FacilityBooking.coach_id.isnot(None),
            FacilityBooking.status == "booked",
        )
    )
    if vid:
        q = q.filter(FacilityBooking.venue_id == vid)
    vids = _scope_vids(_current_user())
    if not vid and vids is not None:
        q = q.filter(FacilityBooking.venue_id.in_(vids)) if vids else q.filter(db.false())
    q = q.order_by(FacilityBooking.booking_date, FacilityBooking.start_time)

    venue_codes = {v.id: v.code for v in Venue.query.all()}
    rows, per_coach = [], {}
    for fb, fac, coach, item, order in q.all():
        if order is not None and order.status == "void":
            continue  # sesi dibatalkan — tak dihitung sbg jam mengajar
        hours = float(item.quantity) if item is not None else 0.0
        revenue = float(item.line_total) if item is not None else 0.0
        persons = fb.coaching_persons or 0
        rows.append({
            "booking_id": fb.id,
            "booking_date": fb.booking_date.isoformat(),
            "start_time": fb.start_time.strftime("%H:%M"),
            "end_time": fb.end_time.strftime("%H:%M"),
            "facility_name": fac.name,
            "venue_code": venue_codes.get(fb.venue_id, f"#{fb.venue_id}"),
            "coach_id": coach.id, "coach_name": coach.name,
            "persons": persons, "hours": hours, "revenue": revenue,
            "customer_name": order.customer_name if order is not None else None,
            "order_number": order.order_number if order is not None else None,
        })
        pc = per_coach.setdefault(coach.id, {
            "coach_id": coach.id, "coach_name": coach.name,
            "sessions": 0, "hours": 0.0, "revenue": 0.0, "persons_total": 0,
        })
        pc["sessions"] += 1
        pc["hours"] += hours
        pc["revenue"] += revenue
        pc["persons_total"] += persons

    for pc in per_coach.values():
        pc["hours"] = round(pc["hours"], 2)
        pc["revenue"] = round(pc["revenue"], 2)

    return jsonify(
        range={"from": d_from, "to": d_to},
        coaches=sorted(per_coach.values(), key=lambda x: -x["revenue"]),
        rows=rows,
        total={
            "sessions": len(rows),
            "hours": round(sum(r["hours"] for r in rows), 2),
            "revenue": round(sum(r["revenue"] for r in rows), 2),
        },
    ), 200


@admin_bp.delete("/bookings/<int:bid>")
@jwt_required()
@ORDER_CANCEL
def booking_delete(bid):
    """Hapus baris booking 'kosong' — sisa test/cancelled tanpa order (order_item_id
    NULL). Booking yg terhubung ke order sungguhan TIDAK boleh dihapus lewat sini
    (pakai Batalkan Booking / hapus order-nya kalau memang perlu)."""
    fb = db.session.get(FacilityBooking, bid)
    if not fb:
        return _err("Booking tidak ditemukan", "not_found", 404)
    vids = _scope_vids(_current_user())
    if vids is not None and fb.venue_id not in vids:
        return _err("Booking di luar cakupan venue Anda", "forbidden", 403)
    if fb.order_item_id is not None:
        return _err(
            "Booking ini terhubung ke order — tak bisa dihapus langsung dari sini.",
            "has_order", 409,
        )
    db.session.delete(fb)
    db.session.commit()
    return jsonify(message="Booking dihapus"), 200


def _norm_phone(p):
    """Normalisasi no HP jadi kunci: hanya digit, awalan 0/62 disamakan → 62..."""
    if not p:
        return None
    d = "".join(ch for ch in str(p) if ch.isdigit())
    if not d:
        return None
    if d.startswith("620"):
        d = "62" + d[3:]
    elif d.startswith("0"):
        d = "62" + d[1:]
    elif not d.startswith("62"):
        d = "62" + d
    return d


def _customer_key(name, phone):
    """Kunci identitas customer: no HP (utama) atau nama (cadangan)."""
    np = _norm_phone(phone)
    if np:
        return "hp:" + np
    nm = (name or "").strip().lower()
    return "nm:" + nm if nm else None


def _booking_order_ids():
    return {
        r[0] for r in db.session.query(OrderItem.order_id)
        .filter(OrderItem.item_type == "booking").distinct().all()
    }


@admin_bp.get("/customers")
@jwt_required()
@VIEW
def customers_list():
    """CRM: daftar customer yang pernah BOOKING, diagregasi dari order (non-void).
    Dikelompokkan per no HP (atau nama bila HP kosong)."""
    bids = _booking_order_ids()
    if not bids:
        return jsonify(count=0, customers=[]), 200
    q = Order.query.filter(Order.status != "void", Order.id.in_(bids))
    forced = _forced_venue()
    if forced is not None:
        q = q.filter(Order.venue_id == forced)
    vmap = {v.id: v.code for v in Venue.query.all()}

    cust = {}
    for o in q.all():
        key = _customer_key(o.customer_name, o.customer_phone)
        if not key:
            continue
        c = cust.get(key)
        if c is None:
            c = cust[key] = {
                "key": key, "name": o.customer_name or "—",
                "phone": o.customer_phone or None, "booking_count": 0,
                "total_spend": 0.0, "total_hours": 0.0, "last_visit": None, "first_seen": None,
                "is_member": False, "_venues": {},
            }
        c["booking_count"] += 1
        c["total_spend"] += float(o.amount_paid or 0)
        # total jam bermain: jumlah durasi (quantity=jam) semua item booking
        c["total_hours"] += float(sum(float(i.quantity or 0) for i in o.items if i.item_type == "booking"))
        if o.is_member:
            c["is_member"] = True
        vc = vmap.get(o.venue_id)
        if vc:
            c["_venues"][vc] = c["_venues"].get(vc, 0) + 1
        dt = o.created_at.isoformat() if o.created_at else None
        if dt:
            if c["last_visit"] is None or dt > c["last_visit"]:
                c["last_visit"] = dt
                if o.customer_name:
                    c["name"] = o.customer_name  # pakai nama dari booking terbaru
                if o.customer_phone:
                    c["phone"] = o.customer_phone
            if c["first_seen"] is None or dt < c["first_seen"]:
                c["first_seen"] = dt

    out = []
    for c in cust.values():
        venues = sorted(c.pop("_venues").items(), key=lambda x: -x[1])
        c["favorite_venue"] = venues[0][0] if venues else None
        c["total_spend"] = round(c["total_spend"], 2)
        c["total_hours"] = round(c["total_hours"], 2)
        out.append(c)
    out.sort(key=lambda x: x["last_visit"] or "", reverse=True)
    return jsonify(count=len(out), customers=out), 200


@admin_bp.get("/customers/history")
@jwt_required()
@VIEW
def customer_history():
    """Riwayat booking 1 customer (dicocokkan lewat kunci HP/nama)."""
    key = request.args.get("key") or _customer_key(request.args.get("name"), request.args.get("phone"))
    if not key:
        return _err("Kunci customer tidak valid", "bad_request")
    bids = _booking_order_ids()
    q = Order.query.filter(Order.status != "void", Order.id.in_(bids))
    forced = _forced_venue()
    if forced is not None:
        q = q.filter(Order.venue_id == forced)
    vmap = {v.id: v.code for v in Venue.query.all()}
    rows = []
    for o in q.order_by(Order.created_at.desc()).all():
        if _customer_key(o.customer_name, o.customer_phone) != key:
            continue
        slots = [i.name_snapshot for i in o.items if i.item_type == "booking"]
        rows.append({
            "order_id": o.id, "order_number": o.order_number,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "venue_code": vmap.get(o.venue_id), "slots": slots,
            "total_amount": float(o.total_amount or 0), "amount_paid": float(o.amount_paid or 0),
            "status": o.status, "is_member": o.is_member,
        })
    return jsonify(count=len(rows), history=rows), 200


@admin_bp.get("/orders")
@jwt_required()
@VIEW
def orders_list():
    """Riwayat transaksi POS — daftar order per venue, dgn tag kategori produk
    per transaksi (utk filter di frontend). manager_unit dipaksa ke venue-nya."""
    d_from, d_to = _date_range()
    forced = _forced_venue()
    vid = forced if forced is not None else request.args.get("venue_id", type=int)
    q = Order.query.filter(func.date(Order.created_at).between(d_from, d_to))
    if vid:
        q = q.filter(Order.venue_id == vid)
    status = request.args.get("status")
    if status:
        q = q.filter(Order.status == status)
    orders = q.order_by(Order.created_at.desc()).limit(300).all()

    uids = {o.cashier_id for o in orders if o.cashier_id}
    users = {u.id: u.username for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}

    order_ids = [o.id for o in orders]
    cats_by_order = {}
    if order_ids:
        cat_rows = (
            db.session.query(OrderItem.order_id, ProductCategory.name)
            .join(Product, OrderItem.product_id == Product.id)
            .join(ProductCategory, Product.category_id == ProductCategory.id)
            .filter(OrderItem.order_id.in_(order_ids))
            .distinct()
            .all()
        )
        for oid, cname in cat_rows:
            cats_by_order.setdefault(oid, []).append(cname)

    rows = []
    for o in orders:
        # basis RIL: hanya payment yg statusnya masih 'paid' (uang yg benar2
        # masuk & belum dibatalkan) — amount_paid di order bisa beda dari ini
        # kalau order sudah dibatalkan setelah lunas (payment ditandai 'void').
        real_paid = sum(float(p.amount) for p in o.payments if p.status == "paid")
        methods = sorted({p.method for p in o.payments if p.status == "paid"})
        rows.append({
            "id": o.id, "order_number": o.order_number, "venue_id": o.venue_id,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "total_amount": float(o.total_amount or 0),
            "amount_paid": round(real_paid, 2),
            "cashier": users.get(o.cashier_id),
            "payment_methods": methods,
            "item_count": len(o.items),
            "categories": sorted(cats_by_order.get(o.id, [])),
        })
    return jsonify(range={"from": d_from, "to": d_to}, count=len(rows), orders=rows), 200


@admin_bp.get("/orders/<int:order_id>")
@jwt_required()
@VIEW
def order_detail(order_id):
    """Detail order + riwayat pembayaran (DP, pelunasan) + kategori per item."""
    order = db.session.get(Order, order_id)
    if not order:
        return _err("Order tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and order.venue_id != forced:
        return _err("Bukan order venue Anda", "forbidden", 403)
    d = order.to_dict()
    prod_ids = [i.product_id for i in order.items if i.product_id]
    cat_map = {}
    if prod_ids:
        cat_map = dict(
            db.session.query(Product.id, ProductCategory.name)
            .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
            .filter(Product.id.in_(prod_ids)).all()
        )
    for it, item_dict in zip(order.items, d["items"]):
        item_dict["category_name"] = cat_map.get(it.product_id)
    cashier = db.session.get(User, order.cashier_id) if order.cashier_id else None
    d["cashier"] = cashier.username if cashier else None
    # riwayat reschedule (slot lama → baru), terbaru dulu
    from ..pos.models import BookingReschedule
    rs = (BookingReschedule.query.filter_by(order_id=order.id)
          .order_by(BookingReschedule.created_at.desc()).all())
    by = {}
    for r in rs:
        if r.created_by and r.created_by not in by:
            u = db.session.get(User, r.created_by)
            by[r.created_by] = u.username if u else None
    d["reschedules"] = [{**r.to_dict(), "by": by.get(r.created_by)} for r in rs]
    # info coaching per item booking — dipakai dialog Reschedule utk tahu coach
    # mana yg terpasang sekarang (coach ada di slot, bukan di order_item)
    item_ids = [i.id for i in order.items if i.item_type == "booking"]
    d["bookings"] = []
    if item_ids:
        coach_names = {c.id: c.name for c in Coach.query.all()}
        for fb in FacilityBooking.query.filter(
            FacilityBooking.order_item_id.in_(item_ids)
        ).all():
            d["bookings"].append({
                "booking_id": fb.id,
                "order_item_id": fb.order_item_id,
                "coach_id": fb.coach_id,
                "coach_name": coach_names.get(fb.coach_id),
                "coaching_persons": fb.coaching_persons,
                "coaching_override": bool(fb.coaching_override),
            })
    return jsonify(order=d), 200


@admin_bp.post("/orders/<int:order_id>/cancel")
@jwt_required()
@ORDER_CANCEL
def order_cancel_admin(order_id):
    """Batalkan transaksi: void + lepas slot. Kalau sudah lunas, balikkan stok
    & akumulasi shift juga (lihat cancel_order untuk aturan lengkapnya)."""
    from ..pos.services import PosError, cancel_order

    order = db.session.get(Order, order_id)
    if not order:
        return _err("Order tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and order.venue_id != forced:
        return _err("Bukan order venue Anda", "forbidden", 403)
    try:
        cancel_order(order, uid=_current_user().id)
    except PosError as e:
        return _err(e.message, e.code, e.status)
    return jsonify(order=order.to_dict(), message="Transaksi dibatalkan"), 200


@admin_bp.post("/orders/<int:order_id>/reschedule")
@jwt_required()
@ORDER_CANCEL
def order_reschedule_admin(order_id):
    """Reschedule booking oleh manajer dari portal (menu Booking). Termasuk
    order yg SUDAH lunas: kalau slot baru lebih murah, kelebihannya dicatat
    otomatis sbg kas keluar di shift terbuka venue (butuh shift terbuka).
    Kalau lebih mahal → order jadi 'partial' (sisa ditagih saat customer bayar
    di POS)."""
    from ..pos.models import Shift
    from ..pos.services import PosError, reschedule_booking

    order = db.session.get(Order, order_id)
    if not order:
        return _err("Order tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and order.venue_id != forced:
        return _err("Bukan order venue Anda", "forbidden", 403)
    d = request.get_json(silent=True) or {}
    for f in ("facility_id", "booking_date", "start_time", "end_time"):
        if not d.get(f):
            return _err(f"{f} wajib diisi")
    # shift terbuka di venue ini utk mencatat refund (kalau ada kelebihan)
    open_shift = (
        Shift.query.filter_by(venue_id=order.venue_id, status="open")
        .order_by(Shift.opened_at.desc())
        .first()
    )
    try:
        order, info = reschedule_booking(
            order, d.get("order_item_id"), d["facility_id"],
            d["booking_date"], d["start_time"], d["end_time"],
            uid=_current_user().id,
            refund_shift_id=open_shift.id if open_shift else None,
            record_refund=True,
            coach_id=d.get("coach_id"),          # opsional: ganti coach
            coach_override=bool(d.get("coach_override")),
        )
    except PosError as e:
        return _err(e.message, e.code, e.status)
    return jsonify(order=order.to_dict(), reschedule=info), 200


@admin_bp.delete("/orders/<int:order_id>")
@jwt_required()
@ORDER_CANCEL
def order_delete_admin(order_id):
    """Hapus permanen transaksi yang SUDAH dibatalkan (status void) — utk
    membersihkan riwayat dari transaksi yang keliru/duplikat. Kalau masih ada
    payment berstatus 'paid' (harusnya sudah 'void' saat dibatalkan, tapi ada
    kasus data lama yang tak konsisten), di-void dulu di sini — supaya tidak
    salah terhitung di laporan manapun. Total shift yang SUDAH ditutup
    sengaja tidak diubah (kas historis yang sudah direkonsiliasi dibiarkan)."""
    order = db.session.get(Order, order_id)
    if not order:
        return _err("Order tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and order.venue_id != forced:
        return _err("Bukan order venue Anda", "forbidden", 403)
    if order.status != "void":
        return _err(
            "Hanya transaksi berstatus Dibatalkan yang bisa dihapus permanen.",
            "bad_status", 409,
        )
    # DP/pendapatan hangus = pembayaran yg masih 'paid' pada order batal (uang
    # ada di shift yg sudah ditutup). Kebijakan: hapus permanen dipakai utk
    # KOREKSI (salah input/dobel) → keluarkan dari kas juga supaya semua laporan
    # konsisten. Maka total shift terkait ikut DIKOREKSI TURUN di sini (bukan
    # cuma buang baris payment). Shift yg masih buka tak ada di sini karena
    # payment-nya sudah di-void & totalnya sudah dibalik saat pembatalan.
    kept = round(sum(float(p.amount) for p in order.payments if p.status == "paid"), 2)
    for p in order.payments:
        if p.status != "paid" or not p.shift_id:
            continue
        shift = db.session.get(Shift, p.shift_id)
        if not shift:
            continue
        amt = float(p.amount)
        shift.total_sales = float(shift.total_sales or 0) - amt
        if p.method == "cash":
            shift.total_cash_sales = float(shift.total_cash_sales or 0) - amt
        elif p.method == "qris":
            shift.total_qris_sales = float(shift.total_qris_sales or 0) - amt
        elif p.method == "transfer":
            shift.total_transfer_sales = float(shift.total_transfer_sales or 0) - amt
    db.session.add(DeletedOrderLog(
        order_number=order.order_number, venue_id=order.venue_id,
        customer_name=order.customer_name, status_before=order.status,
        total_amount=order.total_amount, forfeited_dp=kept,
        deleted_by=_current_user().id,
        note=("Koreksi: Rp %s dikeluarkan dari kas (total shift ikut dikoreksi)."
              % f"{int(kept):,}".replace(",", ".") if kept > 0 else None),
    ))
    db.session.delete(order)  # order_items & payments ikut terhapus (ondelete=CASCADE)
    db.session.commit()
    msg = "Transaksi dihapus permanen"
    if kept > 0:
        msg = f"Transaksi dihapus permanen — Rp {int(kept):,} dikeluarkan dari kas (koreksi)".replace(",", ".")
    return jsonify(message=msg, forfeited_dp=kept), 200


@admin_bp.get("/deleted-orders")
@jwt_required()
@ORDER_CANCEL
def deleted_orders_list():
    """Jejak audit transaksi yg dihapus permanen (tab 'Riwayat Hapus').
    Manager unit hanya lihat venue-nya."""
    q = DeletedOrderLog.query
    forced = _forced_venue()
    if forced is not None:
        q = q.filter(DeletedOrderLog.venue_id == forced)
    elif request.args.get("venue_id", type=int):
        q = q.filter(DeletedOrderLog.venue_id == request.args.get("venue_id", type=int))
    rows = q.order_by(DeletedOrderLog.deleted_at.desc()).limit(500).all()
    emp_names = {e.id: e.name for e in Employee.query.all()}
    users = {u.id: (emp_names.get(u.employee_id) or u.username) for u in User.query.all()}
    return jsonify(logs=[r.to_dict(users) for r in rows]), 200


@admin_bp.get("/reports/outstanding")
@jwt_required()
@VIEW
def report_outstanding():
    """Piutang: order status 'partial' (DP belum lunas)."""
    vid = request.args.get("venue_id", type=int)
    q = Order.query.filter(Order.status == "partial")
    if vid:
        q = q.filter(Order.venue_id == vid)
    orders = q.order_by(Order.created_at.desc()).all()
    rows, total_due = [], 0.0
    for o in orders:
        total = float(o.total_amount or 0)
        paid = float(o.amount_paid or 0)
        due = round(total - paid, 2)
        total_due += due
        rows.append({
            "id": o.id, "order_number": o.order_number, "venue_id": o.venue_id,
            "customer_name": o.customer_name, "customer_phone": o.customer_phone,
            "total": total, "paid": paid, "due": due,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })
    return jsonify(count=len(rows), total_due=round(total_due, 2), orders=rows), 200
