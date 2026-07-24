"""Endpoint admin — kelola master data + laporan. Prefix: /api/admin

Akses: admin & head_office (kelola); reports juga manager_unit.
"""
import calendar
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import Area, Employee, EmployeeDebt, Supplier, User, Venue
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
    vs = Venue.query.order_by(Venue.code).all()
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
            return a.status  # izin | sakit | cuti
        if a and a.check_in:
            return "hadir"
        return "belum" if is_today else "alpha"

    rows, summary = [], {"hadir": 0, "belum": 0, "alpha": 0, "izin": 0, "sakit": 0, "cuti": 0}
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
    if status not in ("izin", "sakit", "cuti", "clear"):
        return _err("status harus izin/sakit/cuti/clear", "bad_request")
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
        Attendance.status.in_(["izin", "sakit", "cuti"]),
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
            "venue_code": vmap.get(r.venue_id), "izin": 0, "sakit": 0, "cuti": 0,
        })
        pe[r.status] = pe.get(r.status, 0) + 1
        detail.append({
            "date": r.date.isoformat(), "name": nm, "venue_code": vmap.get(r.venue_id),
            "status": r.status,
        })
    total = {"izin": 0, "sakit": 0, "cuti": 0}
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
@VIEW
def report_sales():
    d_from, d_to = _date_range()
    vid = request.args.get("venue_id", type=int)

    # --- basis kas: pembayaran yang DITERIMA dalam rentang (DP + pelunasan) ---
    pay_q = (
        db.session.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.status == "paid")
        .filter(func.date(Payment.paid_at).between(d_from, d_to))
    )
    if vid:
        pay_q = pay_q.filter(Order.venue_id == vid)

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
    if vid:
        ord_q = ord_q.filter(Order.venue_id == vid)
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
    q = q.order_by(FacilityBooking.booking_date, FacilityBooking.start_time)

    rows = []
    for fb, fac, order in q.all():
        row = fb.to_dict()
        row["facility_name"] = fac.name
        row["venue_id"] = fb.venue_id
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
        else:
            row["order_total"] = row["order_paid"] = row["order_due"] = None
            row["payment_status"] = None
            row["dp_at"] = row["paid_off_at"] = None
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
    # order void yg DP-nya SUDAH masuk & tidak direfund (payment tetap 'paid' =
    # DP hangus, pendapatan sah yg sudah masuk kas/setoran) TAK BOLEH dihapus —
    # nanti jejak pendapatan hilang & bikin selisih rekonsiliasi. Lihat tab
    # "DP Hangus". Yg boleh dihapus cuma yg tak ada uang tersangkut.
    kept = round(sum(float(p.amount) for p in order.payments if p.status == "paid"), 2)
    if kept > 0:
        return _err(
            "Order ini punya DP hangus yang sudah masuk kas — tak bisa dihapus permanen. "
            "Sembunyikan saja; datanya tetap ada di tab DP Hangus.",
            "has_forfeited_dp", 409,
        )
    db.session.delete(order)  # order_items & payments ikut terhapus (ondelete=CASCADE)
    db.session.commit()
    return jsonify(message="Transaksi dihapus permanen"), 200


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
