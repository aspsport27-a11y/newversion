"""Procurement — supplier, purchase order (approve unit → terima/stok masuk →
bayar HO), lampiran, reorder alert. Prefix: /api/procurement"""
import os
import uuid
from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Supplier, User, Venue
from ..pos.models import Order, OrderItem, Product, StockMovement
from ..security import ROLE_ADMIN_UNIT, ROLE_MANAGER, require_perm
from .models import (
    ConsignmentSettlement,
    ConsignmentSettlementItem,
    PoAttachment,
    PurchaseOrder,
    PurchaseOrderItem,
)

proc_bp = Blueprint("proc", __name__)

# RBAC configurable (izin dikelola via /admin/permissions)
VIEW = require_perm("proc.view")
CREATE = require_perm("proc.create")  # buat/approve/terima PO (wewenang unit)
MANAGE_SUP = require_perm("proc.supplier")
PAY = require_perm("proc.pay")  # bayar = HO/admin

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}


def _err(msg, code="bad_request", status=400):
    return jsonify(error=code, message=msg), status


def _user():
    return db.session.get(User, int(get_jwt_identity()))


def _forced_venue():
    u = _user()
    return u.venue_id if u and u.role == ROLE_MANAGER else None


def _D(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _scope_vids(u):
    """Venue yang boleh diakses. None = semua (admin/HO).
    manager→[venue-nya]; admin_unit→semua venue di areanya."""
    if not u:
        return []
    if u.role == ROLE_MANAGER:
        return [u.venue_id] if u.venue_id else []
    if u.role == ROLE_ADMIN_UNIT:
        return [v.id for v in Venue.query.filter_by(area_id=u.area_id).all()] if u.area_id else []
    return None


def _check_venue(po):
    """Manager/admin_unit hanya boleh dalam cakupannya."""
    vids = _scope_vids(_user())
    if vids is not None and po.venue_id not in vids:
        return _err("PO di luar cakupan Anda", "forbidden", 403)
    return None


# ------------------------------------------------------------------
# Suppliers
# ------------------------------------------------------------------
@proc_bp.get("/suppliers")
@jwt_required()
@VIEW
def suppliers_list():
    sups = Supplier.query.order_by(Supplier.name).all()
    return jsonify(suppliers=[s.to_dict() for s in sups]), 200


def _gen_supplier_code():
    n = (db.session.query(func.count(Supplier.id)).scalar() or 0) + 1
    code = f"SUP-{n:03d}"
    while Supplier.query.filter_by(supplier_code=code).first():
        n += 1
        code = f"SUP-{n:03d}"
    return code


@proc_bp.post("/suppliers")
@jwt_required()
@MANAGE_SUP
def suppliers_create():
    d = request.get_json(silent=True) or {}
    if not d.get("name"):
        return _err("Nama supplier wajib")
    s = Supplier(
        supplier_code=d.get("supplier_code") or _gen_supplier_code(), name=d["name"],
        contact_person=d.get("contact_person"), phone=d.get("phone"), email=d.get("email"),
        address=d.get("address"), city=d.get("city"), payment_terms=d.get("payment_terms"),
        bank_account=d.get("bank_account"), active=bool(d.get("active", True)),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(supplier=s.to_dict()), 201


@proc_bp.post("/suppliers/import")
@jwt_required()
@MANAGE_SUP
def suppliers_import():
    """Import supplier massal dari CSV (percepat entry data awal). Kolom:
    name,contact_person,phone,email,address,city,payment_terms,bank_account
    Hanya 'name' wajib; supplier_code dibuat otomatis seperti entry manual."""
    import csv
    import io

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
        s = Supplier(
            supplier_code=_gen_supplier_code(), name=name,
            contact_person=row.get("contact_person") or None,
            phone=row.get("phone") or None, email=row.get("email") or None,
            address=row.get("address") or None, city=row.get("city") or None,
            payment_terms=row.get("payment_terms") or None,
            bank_account=row.get("bank_account") or None, active=True,
        )
        db.session.add(s)
        db.session.flush()  # supaya _gen_supplier_code baris berikutnya tak tabrakan
        created += 1

    db.session.commit()
    return jsonify(created=created, skipped=skipped), 200


@proc_bp.put("/suppliers/<int:sid>")
@jwt_required()
@MANAGE_SUP
def suppliers_update(sid):
    s = db.session.get(Supplier, sid)
    if not s:
        return _err("Supplier tidak ditemukan", "not_found", 404)
    d = request.get_json(silent=True) or {}
    for f in ("name", "contact_person", "phone", "email", "address", "city", "payment_terms", "bank_account"):
        if f in d:
            setattr(s, f, d[f])
    if "active" in d:
        s.active = bool(d["active"])
    db.session.commit()
    return jsonify(supplier=s.to_dict()), 200


@proc_bp.delete("/suppliers/<int:sid>")
@jwt_required()
@MANAGE_SUP
def suppliers_delete(sid):
    s = db.session.get(Supplier, sid)
    if not s:
        return _err("Supplier tidak ditemukan", "not_found", 404)
    pos = (
        db.session.query(PurchaseOrder, Venue)
        .join(Venue, PurchaseOrder.venue_id == Venue.id)
        .filter(PurchaseOrder.supplier_id == sid).all()
    )
    if pos:
        detail = ", ".join(f"{po.code} @ {v.code}" for po, v in pos[:5])
        more = f" (+{len(pos) - 5} lainnya)" if len(pos) > 5 else ""
        return _err(
            f"Supplier dipakai di PO: {detail}{more} — nonaktifkan saja (jangan hapus).",
            "in_use", 409,
        )
    db.session.delete(s)
    db.session.commit()
    return jsonify(message="Supplier dihapus"), 200


# ------------------------------------------------------------------
# Reorder alert (stok menipis)
# ------------------------------------------------------------------
@proc_bp.get("/reorder")
@jwt_required()
@VIEW
def reorder_list():
    forced = _forced_venue()
    vid = forced if forced is not None else request.args.get("venue_id", type=int)
    q = Product.query.filter(
        Product.is_active.is_(True), Product.track_stock.is_(True),
        db.or_(
            # ambang reorder terlampaui (kalau min_stock di-set)
            db.and_(Product.min_stock > 0, Product.stock_qty <= Product.min_stock),
            # ATAU stok benar2 kosong, walau min_stock belum di-set
            Product.stock_qty <= 0,
        ),
    )
    if vid:
        q = q.filter(Product.venue_id == vid)
    prods = q.order_by(Product.stock_qty).all()
    return jsonify(count=len(prods), products=[p.to_dict() for p in prods]), 200


# ------------------------------------------------------------------
# Purchase Orders
# ------------------------------------------------------------------
def _sup_map():
    return {s.id: s.name for s in Supplier.query.all()}


def _gen_po_code(venue):
    prefix = f"PO-{venue.code}-"
    n = db.session.query(func.count(PurchaseOrder.id)).filter(PurchaseOrder.code.like(prefix + "%")).scalar() or 0
    return f"{prefix}{n + 1:04d}"


@proc_bp.get("/products")
@jwt_required()
@VIEW
def products_for_po():
    """Produk per venue utk form PO — izin proc.view (dipakai manager & admin_unit)."""
    vid = request.args.get("venue_id", type=int)
    vids = _scope_vids(_user())
    q = Product.query.filter_by(is_active=True)
    if vid:
        if vids is not None and vid not in vids:
            return _err("Venue di luar cakupan", "forbidden", 403)
        q = q.filter_by(venue_id=vid)
    elif vids is not None:
        q = q.filter(Product.venue_id.in_(vids)) if vids else q.filter(db.false())
    prods = q.order_by(Product.name).all()
    return jsonify(products=[p.to_dict() for p in prods]), 200


@proc_bp.get("/pos")
@jwt_required()
@VIEW
def pos_list():
    q = PurchaseOrder.query
    vids = _scope_vids(_user())
    if vids is not None:
        q = q.filter(PurchaseOrder.venue_id.in_(vids)) if vids else q.filter(db.false())
    elif request.args.get("venue_id", type=int):
        q = q.filter_by(venue_id=request.args.get("venue_id", type=int))
    if request.args.get("status"):
        q = q.filter_by(status=request.args.get("status"))
    pos = q.order_by(PurchaseOrder.created_at.desc()).all()
    sm = _sup_map()
    return jsonify(count=len(pos), pos=[p.to_dict(sm.get(p.supplier_id)) for p in pos]), 200


@proc_bp.get("/pos/<int:pid>")
@jwt_required()
@VIEW
def po_detail(pid):
    po = db.session.get(PurchaseOrder, pid)
    if not po:
        return _err("PO tidak ditemukan", "not_found", 404)
    err = _check_venue(po)
    if err:
        return err
    return jsonify(po=po.to_dict(_sup_map().get(po.supplier_id))), 200


@proc_bp.post("/pos")
@jwt_required()
@CREATE
def po_create():
    d = request.get_json(silent=True) or {}
    forced = _forced_venue()
    vid = forced if forced is not None else d.get("venue_id")
    if not vid:
        return _err("venue wajib")
    vid = int(vid)
    vids = _scope_vids(_user())
    if vids is not None and vid not in vids:
        return _err("Venue di luar cakupan area Anda", "forbidden", 403)
    venue = db.session.get(Venue, vid)
    if not venue:
        return _err("Venue tidak ditemukan", "not_found", 404)
    items = d.get("items") or []
    if not items:
        return _err("Minimal 1 item")
    po = PurchaseOrder(
        code=_gen_po_code(venue), venue_id=vid, supplier_id=d.get("supplier_id"),
        created_by=_user().id, notes=d.get("notes"), status="submitted",
    )
    total = 0.0
    for it in items:
        qty = int(it.get("quantity") or 0)
        price = _D(it.get("unit_price"))
        if qty <= 0 or price < 0:
            return _err("Item tidak valid (qty > 0)")
        line = qty * price
        total += line
        name = it.get("item_name")
        pid = it.get("product_id")
        if pid:  # ambil nama produk kalau item stok
            prod = db.session.get(Product, pid)
            if prod:
                name = prod.name
        if not name:
            return _err("Nama item wajib")
        po.items.append(PurchaseOrderItem(
            product_id=pid or None, item_name=name[:120], quantity=qty,
            unit=it.get("unit"), unit_price=price, total_price=line, note=it.get("note"),
        ))
    po.total_amount = total
    db.session.add(po)
    db.session.commit()
    return jsonify(po=po.to_dict(_sup_map().get(po.supplier_id))), 201


@proc_bp.post("/pos/<int:pid>/approve")
@jwt_required()
@CREATE
def po_approve(pid):
    po = db.session.get(PurchaseOrder, pid)
    if not po:
        return _err("PO tidak ditemukan", "not_found", 404)
    err = _check_venue(po)
    if err:
        return err
    if po.status != "submitted":
        return _err(f"Status '{po.status}' tak bisa disetujui", "bad_status", 409)
    po.status = "approved"
    po.approved_by = _user().id
    po.approved_at = datetime.utcnow()
    po.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(po=po.to_dict(_sup_map().get(po.supplier_id))), 200


@proc_bp.post("/pos/<int:pid>/reject")
@jwt_required()
@CREATE
def po_reject(pid):
    po = db.session.get(PurchaseOrder, pid)
    if not po:
        return _err("PO tidak ditemukan", "not_found", 404)
    err = _check_venue(po)
    if err:
        return err
    if po.status != "submitted":
        return _err(f"Status '{po.status}' tak bisa ditolak", "bad_status", 409)
    po.status = "rejected"
    po.rejection_reason = (request.get_json(silent=True) or {}).get("reason")
    po.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(po=po.to_dict(_sup_map().get(po.supplier_id))), 200


@proc_bp.post("/pos/<int:pid>/receive")
@jwt_required()
@CREATE
def po_receive(pid):
    """Barang diterima → stok produk masuk (untuk item yang punya product_id)."""
    po = db.session.get(PurchaseOrder, pid)
    if not po:
        return _err("PO tidak ditemukan", "not_found", 404)
    err = _check_venue(po)
    if err:
        return err
    if po.status != "approved":
        return _err("Hanya PO disetujui yang bisa diterima", "bad_status", 409)
    uid = _user().id
    for item in po.items:
        if item.product_id:
            product = db.session.get(Product, item.product_id)
            if product and product.track_stock:
                product.stock_qty = (product.stock_qty or 0) + item.quantity
                db.session.add(StockMovement(
                    product_id=product.id, venue_id=po.venue_id, type="purchase",
                    quantity=item.quantity, balance_after=product.stock_qty,
                    reference=po.code, created_by=uid,
                ))
    po.status = "received"
    po.received_by = uid
    po.received_at = datetime.utcnow()
    po.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(po=po.to_dict(_sup_map().get(po.supplier_id))), 200


@proc_bp.post("/pos/<int:pid>/pay")
@jwt_required()
@PAY
def po_pay(pid):
    po = db.session.get(PurchaseOrder, pid)
    if not po:
        return _err("PO tidak ditemukan", "not_found", 404)
    if po.status != "received":
        return _err("Hanya PO diterima yang bisa dibayar", "bad_status", 409)
    src = (request.get_json(silent=True) or {}).get("source_account_id")
    if src:
        from ..treasury.service import pay_expense
        ok, perr = pay_expense(src, float(po.total_amount), "po", po.id, f"Bayar {po.code}", _user().id)
        if perr:
            return _err(perr)
        po.source_account_id = src
    po.status = "paid"
    po.paid_by = _user().id
    po.paid_at = datetime.utcnow()
    po.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(po=po.to_dict(_sup_map().get(po.supplier_id))), 200


@proc_bp.post("/pos/<int:pid>/revert")
@jwt_required()
@PAY
def po_revert(pid):
    """Batalkan proses PO — kembalikan status ke 'submitted' (Menunggu).
    Kalau sudah 'received'/'paid', balikkan efek stok & kas OTOMATIS: stok
    dikurangi lagi (dicatat sbg penyesuaian, bukan dihapus dr riwayat) & uang
    yg sudah keluar dicatat balik masuk di Kas & Bank. Ditolak kalau sebagian
    stok sudah terjual/terpakai (supaya stok tak jadi minus)."""
    po = db.session.get(PurchaseOrder, pid)
    if not po:
        return _err("PO tidak ditemukan", "not_found", 404)
    err = _check_venue(po)
    if err:
        return err
    if po.status == "submitted":
        return _err("PO sudah berstatus Menunggu", "bad_status", 409)
    uid = _user().id

    if po.status in ("received", "paid"):
        # cek dulu SEMUA item cukup utk dibalik, baru eksekusi (all-or-nothing)
        for item in po.items:
            if item.product_id:
                product = db.session.get(Product, item.product_id)
                if product and product.track_stock and (product.stock_qty or 0) < item.quantity:
                    return _err(
                        f"Stok '{product.name}' sudah berkurang (tersisa {product.stock_qty}, "
                        f"PO ini menambah {item.quantity}) — sebagian sudah terjual/terpakai, "
                        "tidak bisa dibatalkan penuh.",
                        "stock_conflict", 409,
                    )
        for item in po.items:
            if item.product_id:
                product = db.session.get(Product, item.product_id)
                if product and product.track_stock:
                    product.stock_qty = (product.stock_qty or 0) - item.quantity
                    db.session.add(StockMovement(
                        product_id=product.id, venue_id=po.venue_id, type="adjustment",
                        quantity=-item.quantity, balance_after=product.stock_qty,
                        reference=po.code, created_by=uid,
                    ))
        po.received_by = None
        po.received_at = None

    if po.status == "paid" and po.source_account_id:
        from ..treasury.service import record_tx
        record_tx(
            po.source_account_id, "in", float(po.total_amount), "po_cancel",
            ref_type="po", ref_id=po.id, note=f"Pembatalan pembayaran {po.code}",
            user_id=uid,
        )
        po.paid_by = None
        po.paid_at = None
        po.source_account_id = None

    po.status = "submitted"
    po.approved_by = None
    po.approved_at = None
    po.rejection_reason = None
    po.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(po=po.to_dict(_sup_map().get(po.supplier_id))), 200


@proc_bp.delete("/pos/<int:pid>")
@jwt_required()
@CREATE
def po_delete(pid):
    """Hapus PO — hanya sebelum barang diterima/dibayar (blm ada efek stok/kas).
    PO yg sudah 'received'/'paid' TIDAK bisa dihapus (akan merusak riwayat stok/kas)."""
    po = db.session.get(PurchaseOrder, pid)
    if not po:
        return _err("PO tidak ditemukan", "not_found", 404)
    err = _check_venue(po)
    if err:
        return err
    if po.status not in ("submitted", "approved", "rejected"):
        return _err(
            f"PO sudah {po.status} — tidak bisa dihapus (sudah ada efek stok/kas).",
            "bad_status", 409,
        )
    for att in po.attachments:
        path = os.path.join(_upload_dir(), att.stored_name)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(po)  # items & attachments (DB rows) ikut terhapus, ondelete=CASCADE
    db.session.commit()
    return jsonify(message="PO dihapus"), 200


# ------------------------------------------------------------------
# Lampiran (nota/invoice)
# ------------------------------------------------------------------
def _upload_dir():
    d = os.path.join(current_app.config["UPLOAD_FOLDER"], "po")
    os.makedirs(d, exist_ok=True)
    return d


@proc_bp.post("/pos/<int:pid>/attachment")
@jwt_required()
@CREATE
def po_attachment_upload(pid):
    po = db.session.get(PurchaseOrder, pid)
    if not po:
        return _err("PO tidak ditemukan", "not_found", 404)
    err = _check_venue(po)
    if err:
        return err
    if "file" not in request.files:
        return _err("File tidak ada")
    f = request.files["file"]
    if not f.filename:
        return _err("Nama file kosong")
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXT:
        return _err(f"Tipe tidak didukung ({', '.join(sorted(ALLOWED_EXT))})")
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(_upload_dir(), stored)
    f.save(path)
    att = PoAttachment(
        po_id=pid, filename=secure_filename(f.filename), stored_name=stored,
        content_type=f.content_type, size_bytes=os.path.getsize(path),
    )
    db.session.add(att)
    db.session.commit()
    return jsonify(attachment=att.to_dict()), 201


@proc_bp.get("/attachments/<int:aid>")
@jwt_required()
@VIEW
def po_attachment_get(aid):
    att = db.session.get(PoAttachment, aid)
    if not att:
        return _err("Lampiran tidak ditemukan", "not_found", 404)
    po = db.session.get(PurchaseOrder, att.po_id)
    err = _check_venue(po) if po else None
    if err:
        return err
    path = os.path.join(_upload_dir(), att.stored_name)
    if not os.path.exists(path):
        return _err("File hilang di server", "not_found", 404)
    return send_file(path, download_name=att.filename, mimetype=att.content_type)


# ======================================================================
# KONSINYASI (titip barang) — settlement bagi hasil, MANUAL (on-demand)
# Bagi hasil = jumlah TETAP per unit terjual (consignment_price di produk),
# BUKAN persentase. Basis kas: hitung dari Order status='paid' dlm rentang
# tanggal (sama pola dgn laporan penjualan).
# ======================================================================
def _gen_settlement_code(venue):
    prefix = f"KSG-{venue.code}-"
    n = db.session.query(func.count(ConsignmentSettlement.id)).filter(
        ConsignmentSettlement.code.like(prefix + "%")
    ).scalar() or 0
    return f"{prefix}{n + 1:04d}"


def _check_venue_id(venue_id):
    vids = _scope_vids(_user())
    if vids is not None and venue_id not in vids:
        return _err("Venue di luar cakupan Anda", "forbidden", 403)
    return None


@proc_bp.get("/consignment/last-settled")
@jwt_required()
@VIEW
def consignment_last_settled():
    """Tanggal 'period_to' terakhir yg sudah pernah disettle utk venue+supplier
    ini — dipakai frontend menampilkan 'Terakhir disettle sampai: X' spy user
    tak sengaja pilih rentang yg tumpang tindih (dobel hitung)."""
    venue_id = request.args.get("venue_id", type=int)
    supplier_id = request.args.get("supplier_id", type=int)
    if not venue_id or not supplier_id:
        return _err("venue_id & supplier_id wajib")
    err = _check_venue_id(venue_id)
    if err:
        return err
    last = (
        ConsignmentSettlement.query.filter_by(venue_id=venue_id, supplier_id=supplier_id)
        .order_by(ConsignmentSettlement.period_to.desc()).first()
    )
    return jsonify(last_period_to=last.period_to.isoformat() if last else None), 200


@proc_bp.get("/consignment/settlements")
@jwt_required()
@VIEW
def consignment_settlements_list():
    q = ConsignmentSettlement.query
    vids = _scope_vids(_user())
    if vids is not None:
        q = q.filter(ConsignmentSettlement.venue_id.in_(vids)) if vids else q.filter(db.false())
    elif request.args.get("venue_id", type=int):
        q = q.filter_by(venue_id=request.args.get("venue_id", type=int))
    if request.args.get("supplier_id", type=int):
        q = q.filter_by(supplier_id=request.args.get("supplier_id", type=int))
    rows = q.order_by(ConsignmentSettlement.created_at.desc()).all()
    sm = _sup_map()
    return jsonify(count=len(rows), settlements=[s.to_dict(sm.get(s.supplier_id)) for s in rows]), 200


@proc_bp.get("/consignment/settlements/<int:sid>")
@jwt_required()
@VIEW
def consignment_settlement_detail(sid):
    s = db.session.get(ConsignmentSettlement, sid)
    if not s:
        return _err("Settlement tidak ditemukan", "not_found", 404)
    err = _check_venue_id(s.venue_id)
    if err:
        return err
    return jsonify(settlement=s.to_dict(_sup_map().get(s.supplier_id))), 200


@proc_bp.post("/consignment/settlements")
@jwt_required()
@CREATE
def consignment_settlement_create():
    d = request.get_json(silent=True) or {}
    venue_id = d.get("venue_id")
    supplier_id = d.get("supplier_id")
    period_from = d.get("period_from")
    period_to = d.get("period_to")
    if not all([venue_id, supplier_id, period_from, period_to]):
        return _err("venue_id, supplier_id, period_from, period_to wajib")
    venue_id = int(venue_id)
    err = _check_venue_id(venue_id)
    if err:
        return err
    venue = db.session.get(Venue, venue_id)
    if not venue:
        return _err("Venue tidak ditemukan", "not_found", 404)
    if not db.session.get(Supplier, supplier_id):
        return _err("Supplier tidak ditemukan", "not_found", 404)

    products = Product.query.filter_by(
        venue_id=venue_id, supplier_id=supplier_id, is_consignment=True,
    ).all()
    if not products:
        return _err("Tidak ada produk konsinyasi utk supplier ini di venue ini", "no_products", 404)

    # basis kas: order LUNAS yg dibuat dlm rentang (sama pola laporan penjualan)
    paid_ids = [
        o.id for o in Order.query.filter(
            Order.venue_id == venue_id, Order.status == "paid",
            func.date(Order.created_at).between(period_from, period_to),
        ).with_entities(Order.id).all()
    ]

    items = []
    total = 0.0
    if paid_ids:
        for p in products:
            qty = (
                db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0))
                .filter(OrderItem.order_id.in_(paid_ids), OrderItem.product_id == p.id)
                .scalar() or 0
            )
            qty = float(qty)
            if qty <= 0:
                continue
            unit_price = float(p.consignment_price or 0)
            subtotal = round(qty * unit_price, 2)
            items.append(ConsignmentSettlementItem(
                product_id=p.id, product_name=p.name,
                quantity_sold=qty, unit_price=unit_price, subtotal=subtotal,
            ))
            total += subtotal

    if not items:
        return _err(
            "Tidak ada penjualan produk konsinyasi ini pada rentang tanggal tersebut",
            "no_sales", 404,
        )

    s = ConsignmentSettlement(
        code=_gen_settlement_code(venue), venue_id=venue_id, supplier_id=supplier_id,
        period_from=date.fromisoformat(period_from), period_to=date.fromisoformat(period_to),
        total_amount=round(total, 2), notes=d.get("notes"), created_by=_user().id,
    )
    s.items = items
    db.session.add(s)
    db.session.commit()
    return jsonify(settlement=s.to_dict(_sup_map().get(supplier_id))), 201


@proc_bp.post("/consignment/settlements/<int:sid>/pay")
@jwt_required()
@PAY
def consignment_settlement_pay(sid):
    s = db.session.get(ConsignmentSettlement, sid)
    if not s:
        return _err("Settlement tidak ditemukan", "not_found", 404)
    if s.paid_at:
        return _err("Settlement sudah dibayar", "bad_status", 409)
    src = (request.get_json(silent=True) or {}).get("source_account_id")
    if not src:
        return _err("Sumber dana wajib dipilih")
    from ..treasury.service import pay_expense
    ok, perr = pay_expense(src, float(s.total_amount), "consignment", s.id, f"Bagi hasil konsinyasi {s.code}", _user().id)
    if perr:
        return _err(perr)
    s.source_account_id = src
    s.paid_by = _user().id
    s.paid_at = datetime.utcnow()
    db.session.commit()
    return jsonify(settlement=s.to_dict(_sup_map().get(s.supplier_id))), 200


@proc_bp.delete("/consignment/settlements/<int:sid>")
@jwt_required()
@CREATE
def consignment_settlement_delete(sid):
    s = db.session.get(ConsignmentSettlement, sid)
    if not s:
        return _err("Settlement tidak ditemukan", "not_found", 404)
    err = _check_venue_id(s.venue_id)
    if err:
        return err
    if s.paid_at:
        return _err("Settlement sudah dibayar — tidak bisa dihapus.", "bad_status", 409)
    db.session.delete(s)
    db.session.commit()
    return jsonify(message="Settlement dihapus"), 200
