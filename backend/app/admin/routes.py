"""Endpoint admin — kelola master data + laporan. Prefix: /api/admin

Akses: admin & head_office (kelola); reports juga manager_unit.
"""
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import Employee, EmployeeDebt, User, Venue
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
    Promo,
    Shift,
)

admin_bp = Blueprint("admin", __name__)

MANAGE = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE)
VIEW = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)
# HR: manager unit juga boleh kelola karyawan (venue-nya sendiri)
MANAGE_HR = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)

POSITIONS = ["Manager", "Kasir", "Staff Lapangan", "Lifeguard", "Cleaning", "Admin"]


def _current_user():
    return db.session.get(User, int(get_jwt_identity()))


def _forced_venue():
    """Manager unit dibatasi ke venue-nya; admin/head_office bebas (None)."""
    u = _current_user()
    if u and u.role == ROLE_MANAGER:
        return u.venue_id
    return None


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
@MANAGE
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
@MANAGE
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
    v.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(venue=v.to_dict()), 200


@admin_bp.delete("/venues/<int:vid>")
@jwt_required()
@MANAGE
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
    from ..pos.promos import product_public

    items = q.order_by(Product.venue_id, Product.name).all()
    return jsonify(count=len(items), products=[product_public(p) for p in items]), 200


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
        price=_D(d.get("price")), promo_price=_promo(d.get("promo_price")),
        unit=d.get("unit", "pcs"),
        track_stock=bool(d.get("track_stock", True)), stock_qty=int(d.get("stock_qty", 0) or 0),
        min_stock=int(d.get("min_stock", 0) or 0),
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
    if "is_active" in d:
        p.is_active = bool(d["is_active"])
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(product=p.to_dict()), 200


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
    if forced is None and "venue_id" in d:
        e.venue_id = d["venue_id"]
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
    if role not in ("staff", "manager_unit", "head_office", "admin"):
        return _err("role tidak valid")
    if User.query.filter_by(username=username).first():
        return _err("Username sudah dipakai", "duplicate", 409)
    email = e.email or f"{username}@aspsports.id"
    if User.query.filter_by(email=email).first():
        email = f"{username}.{eid}@aspsports.id"
    u = User(username=username, email=email, role=role, active=True,
             venue_id=e.venue_id, employee_id=e.id)
    pin, pw = d.get("pin"), d.get("password")
    if role == "staff":
        if not pin or len(str(pin)) < 4:
            return _err("PIN minimal 4 digit untuk kasir")
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
    q = db.session.query(Promo, Product).join(Product, Promo.product_id == Product.id)
    if vid:
        q = q.filter(Product.venue_id == vid)
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
@MANAGE
def promos_create():
    d = request.get_json(silent=True) or {}
    if not d.get("name") or not d.get("product_id"):
        return _err("name & product_id wajib diisi")
    if not db.session.get(Product, d["product_id"]):
        return _err("Produk tidak ditemukan", "not_found", 404)
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
@MANAGE
def promos_update(pid):
    promo = db.session.get(Promo, pid)
    if not promo:
        return _err("Promo tidak ditemukan", "not_found", 404)
    _promo_from_data(promo, request.get_json(silent=True) or {})
    db.session.commit()
    return jsonify(promo=promo.to_dict()), 200


@admin_bp.delete("/promos/<int:pid>")
@jwt_required()
@MANAGE
def promos_delete(pid):
    promo = db.session.get(Promo, pid)
    if not promo:
        return _err("Promo tidak ditemukan", "not_found", 404)
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
    if paid_ids:
        by_type = [
            {"item_type": t, "amount": float(a)}
            for t, a in db.session.query(
                OrderItem.item_type, func.coalesce(func.sum(OrderItem.line_total), 0)
            ).filter(OrderItem.order_id.in_(paid_ids)).group_by(OrderItem.item_type).all()
        ]

    return jsonify(
        range={"from": d_from, "to": d_to},
        total_revenue=total_received,
        order_count=payment_count,
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
        else:
            row["order_total"] = row["order_paid"] = row["order_due"] = None
            row["payment_status"] = None
        rows.append(row)
    return jsonify(range={"from": d_from, "to": d_to}, count=len(rows), bookings=rows), 200


@admin_bp.get("/orders/<int:order_id>")
@jwt_required()
@VIEW
def order_detail(order_id):
    """Detail order + riwayat pembayaran (DP, pelunasan)."""
    order = db.session.get(Order, order_id)
    if not order:
        return _err("Order tidak ditemukan", "not_found", 404)
    return jsonify(order=order.to_dict()), 200


@admin_bp.post("/orders/<int:order_id>/cancel")
@jwt_required()
@MANAGE
def order_cancel_admin(order_id):
    """Batalkan booking (no-show): void + lepas slot, DP hangus."""
    from ..pos.services import PosError, cancel_order

    order = db.session.get(Order, order_id)
    if not order:
        return _err("Order tidak ditemukan", "not_found", 404)
    try:
        cancel_order(order)
    except PosError as e:
        return _err(e.message, e.code, e.status)
    return jsonify(order=order.to_dict()), 200


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
