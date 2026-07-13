"""Operasional & Budget — kategori, plafon budget, pengajuan dana (approval +
pencairan), lampiran bukti. Prefix: /api/ops"""
import os
import uuid
from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import User, Venue
from ..security import ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, roles_required
from .models import (
    Budget,
    ExpenseCategory,
    OpRequest,
    OpRequestAttachment,
    OpRequestItem,
)

ops_bp = Blueprint("ops", __name__)

VIEW = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)
CREATE = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)
APPROVE = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE)  # Head Office/Admin

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}


def _err(msg, code="bad_request", status=400):
    return jsonify(error=code, message=msg), status


def _user():
    return db.session.get(User, int(get_jwt_identity()))


def _forced_venue():
    u = _user()
    return u.venue_id if u and u.role == ROLE_MANAGER else None


def _cat_map():
    return {c.id: c.name for c in ExpenseCategory.query.all()}


def _D(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------
# Kategori
# ------------------------------------------------------------------
@ops_bp.get("/categories")
@jwt_required()
@VIEW
def categories_list():
    cats = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.sort_order).all()
    return jsonify(categories=[c.to_dict() for c in cats]), 200


@ops_bp.post("/categories")
@jwt_required()
@APPROVE
def categories_create():
    d = request.get_json(silent=True) or {}
    if not d.get("name"):
        return _err("Nama kategori wajib")
    if ExpenseCategory.query.filter_by(name=d["name"]).first():
        return _err("Kategori sudah ada", "duplicate", 409)
    c = ExpenseCategory(name=d["name"], sort_order=int(d.get("sort_order", 99)))
    db.session.add(c)
    db.session.commit()
    return jsonify(category=c.to_dict()), 201


# ------------------------------------------------------------------
# Budget (plafon) + realisasi
# ------------------------------------------------------------------
def _used_by_category(venue_id, year, month):
    rows = (
        db.session.query(OpRequestItem.category_id, func.coalesce(func.sum(OpRequestItem.amount), 0))
        .join(OpRequest, OpRequestItem.request_id == OpRequest.id)
        .filter(
            OpRequest.venue_id == venue_id,
            OpRequest.period_year == year,
            OpRequest.period_month == month,
            OpRequest.status.in_(("approved", "disbursed")),
        )
        .group_by(OpRequestItem.category_id)
        .all()
    )
    return {cid: float(amt) for cid, amt in rows}


@ops_bp.get("/budgets")
@jwt_required()
@VIEW
def budgets_list():
    forced = _forced_venue()
    vid = forced if forced is not None else request.args.get("venue_id", type=int)
    if not vid:
        return _err("venue_id wajib")
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month

    plafon = {
        b.category_id: float(b.amount)
        for b in Budget.query.filter_by(venue_id=vid, year=year, month=month).all()
    }
    used = _used_by_category(vid, year, month)
    cats = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.sort_order).all()
    rows = []
    for c in cats:
        p = plafon.get(c.id, 0.0)
        u = used.get(c.id, 0.0)
        rows.append({
            "category_id": c.id, "category_name": c.name,
            "budget": p, "used": u, "remaining": round(p - u, 2),
        })
    return jsonify(
        venue_id=vid, year=year, month=month,
        total_budget=round(sum(r["budget"] for r in rows), 2),
        total_used=round(sum(r["used"] for r in rows), 2),
        rows=rows,
    ), 200


@ops_bp.post("/budgets")
@jwt_required()
@APPROVE
def budgets_set():
    """Set/ubah plafon per kategori untuk venue/bulan (upsert)."""
    d = request.get_json(silent=True) or {}
    vid = d.get("venue_id")
    year = d.get("year")
    month = d.get("month")
    items = d.get("items") or []  # [{category_id, amount}]
    if not vid or not year or not month:
        return _err("venue_id, year, month wajib")
    for it in items:
        cid = it.get("category_id")
        amt = _D(it.get("amount"))
        b = Budget.query.filter_by(venue_id=vid, year=year, month=month, category_id=cid).first()
        if b:
            b.amount = amt
            b.updated_at = datetime.utcnow()
        else:
            db.session.add(Budget(venue_id=vid, year=year, month=month, category_id=cid, amount=amt))
    db.session.commit()
    return jsonify(message="Budget disimpan"), 200


# ------------------------------------------------------------------
# Pengajuan (op_requests)
# ------------------------------------------------------------------
def _gen_code(venue, year, month):
    prefix = f"OPS-{venue.code}-{year}{month:02d}-"
    n = (
        db.session.query(func.count(OpRequest.id))
        .filter(OpRequest.code.like(prefix + "%")).scalar() or 0
    )
    return f"{prefix}{n + 1:03d}"


@ops_bp.get("/requests")
@jwt_required()
@VIEW
def requests_list():
    q = OpRequest.query
    forced = _forced_venue()
    if forced is not None:
        q = q.filter_by(venue_id=forced)
    elif request.args.get("venue_id", type=int):
        q = q.filter_by(venue_id=request.args.get("venue_id", type=int))
    if request.args.get("status"):
        q = q.filter_by(status=request.args.get("status"))
    reqs = q.order_by(OpRequest.created_at.desc()).all()
    cats = _cat_map()
    return jsonify(count=len(reqs), requests=[r.to_dict(cats) for r in reqs]), 200


@ops_bp.get("/requests/<int:rid>")
@jwt_required()
@VIEW
def request_detail(rid):
    r = db.session.get(OpRequest, rid)
    if not r:
        return _err("Pengajuan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and r.venue_id != forced:
        return _err("Bukan pengajuan venue Anda", "forbidden", 403)
    d = r.to_dict(_cat_map())
    # konteks budget per kategori
    plafon = {b.category_id: float(b.amount) for b in Budget.query.filter_by(venue_id=r.venue_id, year=r.period_year, month=r.period_month).all()}
    used = _used_by_category(r.venue_id, r.period_year, r.period_month)
    for it in d["items"]:
        cid = it["category_id"]
        it["budget"] = plafon.get(cid, 0.0)
        it["budget_remaining"] = round(plafon.get(cid, 0.0) - used.get(cid, 0.0), 2)
    return jsonify(request=d), 200


@ops_bp.post("/requests")
@jwt_required()
@CREATE
def request_create():
    d = request.get_json(silent=True) or {}
    forced = _forced_venue()
    vid = forced if forced is not None else d.get("venue_id")
    if not vid:
        return _err("venue wajib")
    venue = db.session.get(Venue, vid)
    if not venue:
        return _err("Venue tidak ditemukan", "not_found", 404)
    items = d.get("items") or []
    if not items:
        return _err("Minimal 1 rincian")
    today = date.today()
    month = int(d.get("period_month") or today.month)
    year = int(d.get("period_year") or today.year)

    r = OpRequest(
        code=_gen_code(venue, year, month), venue_id=vid, period_month=month,
        period_year=year, created_by=_user().id, description=d.get("description"),
        status="submitted",
    )
    total = 0.0
    for it in items:
        amt = _D(it.get("amount"))
        if not it.get("category_id") or amt <= 0:
            return _err("Rincian tidak valid (kategori & jumlah > 0)")
        total += amt
        r.items.append(OpRequestItem(category_id=it["category_id"], amount=amt, note=it.get("note")))
    r.total_amount = total
    db.session.add(r)
    db.session.commit()
    return jsonify(request=r.to_dict(_cat_map())), 201


@ops_bp.post("/requests/<int:rid>/approve")
@jwt_required()
@APPROVE
def request_approve(rid):
    r = db.session.get(OpRequest, rid)
    if not r:
        return _err("Pengajuan tidak ditemukan", "not_found", 404)
    if r.status != "submitted":
        return _err(f"Status '{r.status}' tak bisa disetujui", "bad_status", 409)
    r.status = "approved"
    r.approved_by = _user().id
    r.approved_at = datetime.utcnow()
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(request=r.to_dict(_cat_map())), 200


@ops_bp.post("/requests/<int:rid>/reject")
@jwt_required()
@APPROVE
def request_reject(rid):
    r = db.session.get(OpRequest, rid)
    if not r:
        return _err("Pengajuan tidak ditemukan", "not_found", 404)
    if r.status != "submitted":
        return _err(f"Status '{r.status}' tak bisa ditolak", "bad_status", 409)
    d = request.get_json(silent=True) or {}
    r.status = "rejected"
    r.rejection_reason = d.get("reason")
    r.approved_by = _user().id
    r.approved_at = datetime.utcnow()
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(request=r.to_dict(_cat_map())), 200


@ops_bp.post("/requests/<int:rid>/disburse")
@jwt_required()
@APPROVE
def request_disburse(rid):
    r = db.session.get(OpRequest, rid)
    if not r:
        return _err("Pengajuan tidak ditemukan", "not_found", 404)
    if r.status != "approved":
        return _err("Hanya pengajuan disetujui yang bisa dicairkan", "bad_status", 409)
    src = (request.get_json(silent=True) or {}).get("source_account_id")
    if src:
        from ..treasury.service import pay_expense
        ok, perr = pay_expense(src, float(r.total_amount), "op_request", r.id, f"Pencairan {r.code}", _user().id)
        if perr:
            return _err(perr)
        r.source_account_id = src
    r.status = "disbursed"
    r.disbursed_by = _user().id
    r.disbursed_at = datetime.utcnow()
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(request=r.to_dict(_cat_map())), 200


# ------------------------------------------------------------------
# Lampiran bukti
# ------------------------------------------------------------------
def _upload_dir():
    d = os.path.join(current_app.config["UPLOAD_FOLDER"], "oprequests")
    os.makedirs(d, exist_ok=True)
    return d


@ops_bp.post("/requests/<int:rid>/attachment")
@jwt_required()
@CREATE
def attachment_upload(rid):
    r = db.session.get(OpRequest, rid)
    if not r:
        return _err("Pengajuan tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and r.venue_id != forced:
        return _err("Bukan pengajuan venue Anda", "forbidden", 403)
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
    att = OpRequestAttachment(
        request_id=rid, filename=secure_filename(f.filename), stored_name=stored,
        content_type=f.content_type, size_bytes=os.path.getsize(path),
    )
    db.session.add(att)
    db.session.commit()
    return jsonify(attachment=att.to_dict()), 201


@ops_bp.get("/attachments/<int:aid>")
@jwt_required()
@VIEW
def attachment_get(aid):
    att = db.session.get(OpRequestAttachment, aid)
    if not att:
        return _err("Lampiran tidak ditemukan", "not_found", 404)
    r = db.session.get(OpRequest, att.request_id)
    forced = _forced_venue()
    if forced is not None and r and r.venue_id != forced:
        return _err("Bukan lampiran venue Anda", "forbidden", 403)
    path = os.path.join(_upload_dir(), att.stored_name)
    if not os.path.exists(path):
        return _err("File hilang di server", "not_found", 404)
    return send_file(path, download_name=att.filename, mimetype=att.content_type)
