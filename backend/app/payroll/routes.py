"""Payroll — generate gaji (auto hitung + potong kasbon), approval, pembayaran.
Prefix: /api/payroll"""
import os
import uuid
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Employee, EmployeeDebt, User, Venue
from ..security import ROLE_MANAGER, require_perm
from .models import Overtime, OvertimeRun, PayrollAttachment, PayrollItem, PayrollRun

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}

payroll_bp = Blueprint("payroll", __name__)

# RBAC configurable (izin dikelola via /admin/permissions)
VIEW = require_perm("payroll.view")
CREATE = require_perm("payroll.generate")  # unit generate
APPROVE = require_perm("payroll.approve")  # HO approve & pay


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


def _kasbon_balance(emp_id):
    adv = db.session.query(func.coalesce(func.sum(EmployeeDebt.amount), 0)).filter_by(employee_id=emp_id, type="advance").scalar() or 0
    rep = db.session.query(func.coalesce(func.sum(EmployeeDebt.amount), 0)).filter_by(employee_id=emp_id, type="repayment").scalar() or 0
    return round(float(adv) - float(rep), 2)


def _check_venue(run):
    forced = _forced_venue()
    if forced is not None and run.venue_id != forced:
        return _err("Bukan payroll venue Anda", "forbidden", 403)
    return None


def _recalc(item):
    item.net_salary = (
        _D(item.base_salary) + _D(item.allowance)
        - _D(item.kasbon_deduction) - _D(item.other_deduction)
    )


# ------------------------------------------------------------------
@payroll_bp.get("/runs")
@jwt_required()
@VIEW
def runs_list():
    q = PayrollRun.query
    forced = _forced_venue()
    if forced is not None:
        q = q.filter_by(venue_id=forced)
    elif request.args.get("venue_id", type=int):
        q = q.filter_by(venue_id=request.args.get("venue_id", type=int))
    if request.args.get("status"):
        q = q.filter_by(status=request.args.get("status"))
    runs = q.order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc()).all()
    return jsonify(count=len(runs), runs=[r.to_dict() for r in runs]), 200


@payroll_bp.get("/runs/<int:rid>")
@jwt_required()
@VIEW
def run_detail(rid):
    r = db.session.get(PayrollRun, rid)
    if not r:
        return _err("Payroll tidak ditemukan", "not_found", 404)
    err = _check_venue(r)
    if err:
        return err
    return jsonify(run=r.to_dict(with_items=True)), 200


@payroll_bp.post("/runs")
@jwt_required()
@CREATE
def run_generate():
    """Generate payroll untuk semua karyawan aktif di venue + periode."""
    d = request.get_json(silent=True) or {}
    forced = _forced_venue()
    vid = forced if forced is not None else d.get("venue_id")
    if not vid:
        return _err("venue wajib")
    venue = db.session.get(Venue, vid)
    if not venue:
        return _err("Venue tidak ditemukan", "not_found", 404)
    month, year = int(d.get("period_month")), int(d.get("period_year"))
    if PayrollRun.query.filter_by(venue_id=vid, period_year=year, period_month=month).first():
        return _err("Payroll periode ini sudah ada", "duplicate", 409)
    emps = Employee.query.filter_by(venue_id=vid, status="active").order_by(Employee.name).all()
    if not emps:
        return _err("Tidak ada karyawan aktif di venue ini")

    run = PayrollRun(
        code=f"PAY-{venue.code}-{year}{month:02d}", venue_id=vid, period_month=month,
        period_year=year, created_by=_user().id, status="draft",
    )
    total = 0.0
    for e in emps:
        base = _D(e.salary)
        allow = _D(e.allowance)
        inst = _D(e.kasbon_installment)
        bal = _kasbon_balance(e.id)
        kasbon = round(min(inst, bal), 2) if inst > 0 and bal > 0 else 0.0
        net = base + allow - kasbon
        total += net
        run.items.append(PayrollItem(
            employee_id=e.id, employee_name=e.name, position=e.position,
            base_salary=base, allowance=allow, kasbon_deduction=kasbon,
            other_deduction=0, net_salary=net, bank_name=e.bank_name, bank_account=e.bank_account,
        ))
    run.total_net = total
    db.session.add(run)
    db.session.commit()
    return jsonify(run=run.to_dict(with_items=True)), 201


@payroll_bp.put("/items/<int:iid>")
@jwt_required()
@CREATE
def item_update(iid):
    item = db.session.get(PayrollItem, iid)
    if not item:
        return _err("Item tidak ditemukan", "not_found", 404)
    run = db.session.get(PayrollRun, item.run_id)
    err = _check_venue(run)
    if err:
        return err
    if run.status not in ("draft", "submitted"):
        return _err("Payroll sudah diproses, tak bisa diubah", "locked", 409)
    d = request.get_json(silent=True) or {}
    if "allowance" in d:
        item.allowance = _D(d["allowance"])
    if "other_deduction" in d:
        item.other_deduction = _D(d["other_deduction"])
    if "note" in d:
        item.note = d["note"]
    _recalc(item)
    # update total run
    run.total_net = sum(_D(i.net_salary) for i in run.items)
    run.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(item=item.to_dict(), total_net=float(run.total_net)), 200


# ------------------------------------------------------------------
# Entri manual berkategori — Lembur, Reward, Pekerjaan Tambahan (tab terpisah,
# konsep sama). Alur approval seperti payroll: draft → submitted (diajukan ke HO)
# → approved/rejected. Belum diikat ke perhitungan gaji; baru pencatatan + approval.
# ------------------------------------------------------------------
OT_CATEGORIES = ("lembur", "reward", "tambahan")


def _ot_cat(source=None):
    """Ambil kategori dari query/body; default 'lembur'; validasi ke daftar."""
    if source is None:
        source = request.args if request.method == "GET" else (request.get_json(silent=True) or {})
    c = (source.get("category") or "lembur")
    return c if c in OT_CATEGORIES else "lembur"


def _ot_run(vid, year, month, cat, create=False):
    r = OvertimeRun.query.filter_by(
        venue_id=vid, period_year=int(year), period_month=int(month), category=cat).first()
    if not r and create:
        r = OvertimeRun(venue_id=vid, period_year=int(year), period_month=int(month),
                        category=cat, status="draft", created_by=_user().id)
        db.session.add(r)
    return r


def _ot_total(vid, year, month, cat):
    t = db.session.query(func.coalesce(func.sum(Overtime.amount), 0)).filter_by(
        venue_id=vid, period_year=int(year), period_month=int(month), category=cat).scalar() or 0
    return round(float(t), 2)


@payroll_bp.get("/overtime")
@jwt_required()
@VIEW
def overtime_list():
    """Daftar karyawan aktif di venue + nilai (kategori) periode itu (0 bila belum
    ada), beserta status batch."""
    forced = _forced_venue()
    vid = forced if forced is not None else request.args.get("venue_id", type=int)
    if not vid:
        return _err("venue wajib")
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    if not year or not month:
        return _err("periode wajib")
    cat = _ot_cat()

    emps = Employee.query.filter_by(venue_id=vid, status="active").order_by(Employee.name).all()
    existing = {
        o.employee_id: o
        for o in Overtime.query.filter_by(venue_id=vid, period_year=year, period_month=month, category=cat).all()
    }
    rows, total = [], 0.0
    for e in emps:
        o = existing.get(e.id)
        amt = float(o.amount) if o else 0.0
        total += amt
        rows.append({
            "employee_id": e.id, "employee_name": e.name, "position": e.position,
            "amount": amt, "note": o.note if o else None,
        })
    run = _ot_run(vid, year, month, cat)
    return jsonify(
        count=len(rows), total=round(total, 2), items=rows,
        run=run.to_dict() if run else {"status": "draft", "total_amount": round(total, 2)},
    ), 200


@payroll_bp.put("/overtime/bulk")
@jwt_required()
@CREATE
def overtime_bulk():
    """Simpan banyak entri sekaligus ('Simpan Semua'). Hanya saat draft/rejected."""
    d = request.get_json(silent=True) or {}
    year, month = d.get("period_year"), d.get("period_month")
    if not year or not month:
        return _err("periode wajib")
    forced = _forced_venue()
    vid = forced if forced is not None else d.get("venue_id")
    if not vid:
        return _err("venue wajib")
    cat = _ot_cat(d)
    run = _ot_run(vid, year, month, cat)
    if run and run.status in ("submitted", "approved"):
        return _err("Sudah diajukan/disetujui — tak bisa diubah", "locked", 409)

    uid = _user().id
    saved = 0
    for it in (d.get("items") or []):
        emp_id = it.get("employee_id")
        if not emp_id:
            continue
        emp = db.session.get(Employee, emp_id)
        if not emp or (forced is not None and emp.venue_id != forced):
            continue
        amount = _D(it.get("amount"))
        note = (it.get("note") or None)
        o = Overtime.query.filter_by(
            employee_id=emp_id, period_year=int(year), period_month=int(month), category=cat,
        ).first()
        if not o:
            if amount == 0 and not note:
                continue  # jangan bikin entri kosong (0 tanpa catatan)
            o = Overtime(employee_id=emp_id, venue_id=emp.venue_id, category=cat,
                         period_year=int(year), period_month=int(month))
            db.session.add(o)
        o.amount = amount
        o.note = note
        o.updated_by = uid
        o.updated_at = datetime.utcnow()
        saved += 1

    run = _ot_run(vid, year, month, cat, create=True)
    run.status = "draft"  # simpan ulang setelah ditolak → balik draft
    run.rejection_reason = None
    db.session.flush()
    run.total_amount = _ot_total(vid, year, month, cat)
    run.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(ok=True, saved=saved, run=run.to_dict()), 200


@payroll_bp.post("/overtime/submit")
@jwt_required()
@CREATE
def overtime_submit():
    """Ajukan batch venue+periode+kategori ke HO (draft/rejected → submitted)."""
    d = request.get_json(silent=True) or {}
    year, month = d.get("period_year"), d.get("period_month")
    forced = _forced_venue()
    vid = forced if forced is not None else d.get("venue_id")
    if not vid or not year or not month:
        return _err("venue & periode wajib")
    cat = _ot_cat(d)
    run = _ot_run(vid, year, month, cat, create=True)
    if run.status not in ("draft", "rejected"):
        return _err(f"Status '{run.status}' tak bisa diajukan", "bad_status", 409)
    db.session.flush()
    run.total_amount = _ot_total(vid, year, month, cat)
    if run.total_amount <= 0:
        return _err("Belum ada nilai untuk diajukan")
    run.status = "submitted"
    run.submitted_at = datetime.utcnow()
    run.rejection_reason = None
    run.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(run=run.to_dict()), 200


def _ot_review(new_status, allowed_from="submitted"):
    d = request.get_json(silent=True) or {}
    vid = d.get("venue_id")
    year, month = d.get("period_year"), d.get("period_month")
    if not vid or not year or not month:
        return None, _err("venue & periode wajib")
    run = _ot_run(vid, year, month, _ot_cat(d))
    if not run:
        return None, _err("Pengajuan tidak ditemukan", "not_found", 404)
    if run.status != allowed_from:
        return None, _err(f"Status '{run.status}' tak bisa ke '{new_status}'", "bad_status", 409)
    return run, None


@payroll_bp.post("/overtime/approve")
@jwt_required()
@APPROVE
def overtime_approve():
    run, err = _ot_review("approved")
    if err:
        return err
    run.status = "approved"
    run.approved_by = _user().id
    run.approved_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(run=run.to_dict()), 200


@payroll_bp.post("/overtime/reject")
@jwt_required()
@APPROVE
def overtime_reject():
    run, err = _ot_review("rejected")
    if err:
        return err
    d = request.get_json(silent=True) or {}
    run.status = "rejected"
    run.rejection_reason = d.get("reason")
    run.approved_by = _user().id
    run.approved_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(run=run.to_dict()), 200


@payroll_bp.get("/overtime/pending-count")
@jwt_required()
@VIEW
def overtime_pending_count():
    """Jumlah pengajuan submitted per kategori (utk notifikasi HO)."""
    forced = _forced_venue()
    q = OvertimeRun.query.filter_by(status="submitted")
    if forced is not None:
        q = q.filter_by(venue_id=forced)
    counts = {c: 0 for c in OT_CATEGORIES}
    for r in q.all():
        if r.category in counts:
            counts[r.category] += 1
    return jsonify(counts=counts, count=sum(counts.values())), 200


@payroll_bp.get("/overtime/runs")
@jwt_required()
@VIEW
def overtime_runs_list():
    """Daftar batch (baris seperti payroll) utk 1 kategori — venue, periode, status,
    total, jumlah karyawan terisi. Scope venue seperti payroll."""
    forced = _forced_venue()
    cat = _ot_cat()
    q = OvertimeRun.query.filter_by(category=cat)
    if forced is not None:
        q = q.filter_by(venue_id=forced)
    elif request.args.get("venue_id", type=int):
        q = q.filter_by(venue_id=request.args.get("venue_id", type=int))
    runs = q.order_by(
        OvertimeRun.period_year.desc(), OvertimeRun.period_month.desc(), OvertimeRun.id.desc()
    ).all()
    out = []
    for r in runs:
        d = r.to_dict()
        d["employee_count"] = Overtime.query.filter_by(
            venue_id=r.venue_id, period_year=r.period_year, period_month=r.period_month, category=cat
        ).count()
        out.append(d)
    return jsonify(count=len(out), runs=out), 200


@payroll_bp.post("/overtime/runs")
@jwt_required()
@CREATE
def overtime_run_create():
    """Buat batch (draft) utk venue+periode+kategori — mirip 'Generate Gaji'."""
    d = request.get_json(silent=True) or {}
    year, month = d.get("period_year"), d.get("period_month")
    forced = _forced_venue()
    vid = forced if forced is not None else d.get("venue_id")
    if not vid or not year or not month:
        return _err("venue & periode wajib")
    cat = _ot_cat(d)
    if not db.session.get(Venue, vid):
        return _err("Venue tidak ditemukan", "not_found", 404)
    if OvertimeRun.query.filter_by(venue_id=vid, period_year=int(year), period_month=int(month), category=cat).first():
        return _err("Periode ini sudah ada", "duplicate", 409)
    if not Employee.query.filter_by(venue_id=vid, status="active").first():
        return _err("Tidak ada karyawan aktif di venue ini")
    run = OvertimeRun(venue_id=vid, period_year=int(year), period_month=int(month),
                      category=cat, status="draft", created_by=_user().id)
    db.session.add(run)
    db.session.commit()
    return jsonify(run=run.to_dict()), 201


@payroll_bp.delete("/overtime/runs/<int:rid>")
@jwt_required()
@CREATE
def overtime_run_delete(rid):
    """Hapus batch + entrinya — hanya draft/rejected (belum diajukan)."""
    run = db.session.get(OvertimeRun, rid)
    if not run:
        return _err("Tidak ditemukan", "not_found", 404)
    forced = _forced_venue()
    if forced is not None and run.venue_id != forced:
        return _err("Bukan venue Anda", "forbidden", 403)
    if run.status in ("submitted", "approved"):
        return _err("Sudah diajukan/disetujui — tak bisa dihapus", "locked", 409)
    Overtime.query.filter_by(
        venue_id=run.venue_id, period_year=run.period_year, period_month=run.period_month, category=run.category
    ).delete()
    db.session.delete(run)
    db.session.commit()
    return jsonify(ok=True), 200


@payroll_bp.get("/overtime/summary")
@jwt_required()
@VIEW
def overtime_summary():
    """Ringkasan 1 kategori per status (jumlah + total Rp), sesuai scope — utk
    kartu stiker per status."""
    forced = _forced_venue()
    q = OvertimeRun.query.filter_by(category=_ot_cat())
    if forced is not None:
        q = q.filter_by(venue_id=forced)
    out = {s: {"count": 0, "total": 0.0} for s in ("draft", "submitted", "approved", "rejected")}
    for r in q.all():
        s = r.status if r.status in out else "draft"
        out[s]["count"] += 1
        out[s]["total"] += float(r.total_amount or 0)
    for s in out:
        out[s]["total"] = round(out[s]["total"], 2)
    return jsonify(summary=out), 200


def _transition(rid, allowed_from, new_status, extra=None):
    r = db.session.get(PayrollRun, rid)
    if not r:
        return None, _err("Payroll tidak ditemukan", "not_found", 404)
    if r.status != allowed_from:
        return None, _err(f"Status '{r.status}' tak bisa ke '{new_status}'", "bad_status", 409)
    return r, None


@payroll_bp.post("/runs/<int:rid>/submit")
@jwt_required()
@CREATE
def run_submit(rid):
    r, err = _transition(rid, "draft", "submitted")
    if err:
        return err
    verr = _check_venue(r)
    if verr:
        return verr
    r.status = "submitted"
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(run=r.to_dict()), 200


@payroll_bp.post("/runs/<int:rid>/approve")
@jwt_required()
@APPROVE
def run_approve(rid):
    r, err = _transition(rid, "submitted", "approved")
    if err:
        return err
    r.status = "approved"
    r.approved_by = _user().id
    r.approved_at = datetime.utcnow()
    db.session.commit()
    return jsonify(run=r.to_dict()), 200


@payroll_bp.post("/runs/<int:rid>/reject")
@jwt_required()
@APPROVE
def run_reject(rid):
    r, err = _transition(rid, "submitted", "rejected")
    if err:
        return err
    r.status = "rejected"
    r.rejection_reason = (request.get_json(silent=True) or {}).get("reason")
    db.session.commit()
    return jsonify(run=r.to_dict()), 200


@payroll_bp.post("/runs/<int:rid>/pay")
@jwt_required()
@APPROVE
def run_pay(rid):
    """Bayar (transfer). Nominal transfer bisa dientry manual (mis. beda krn
    pembulatan/penyesuaian di luar sistem) — default = total gaji bersih
    kalau tak diisi. Status tetap langsung 'paid' penuh berapa pun nominalnya
    (sistem tak melacak sisa kekurangan). Eksekusi potong kasbon → employee_debts
    repayment tetap dihitung dari total_net (bukan nominal transfer)."""
    r, err = _transition(rid, "approved", "paid")
    if err:
        return err
    uid = _user().id
    d = request.get_json(silent=True) or {}
    src = d.get("source_account_id")
    amount = _D(d.get("amount")) if d.get("amount") not in (None, "", 0, "0") else float(r.total_net)
    if amount <= 0:
        return _err("Nominal transfer harus lebih dari 0")
    if src:
        from ..treasury.service import pay_expense
        ok, perr = pay_expense(src, amount, "payroll", r.id, f"Gaji {r.code}", uid)
        if perr:
            return _err(perr)
        r.source_account_id = src
    r.paid_amount = amount
    for item in r.items:
        if _D(item.kasbon_deduction) > 0 and item.employee_id:
            bal = _kasbon_balance(item.employee_id)
            rep = round(min(_D(item.kasbon_deduction), bal), 2)
            if rep > 0:
                db.session.add(EmployeeDebt(
                    employee_id=item.employee_id, type="repayment", amount=rep,
                    note=f"Potong gaji {r.code}", created_by=uid,
                ))
    r.status = "paid"
    r.paid_by = uid
    r.paid_at = datetime.utcnow()
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(run=r.to_dict()), 200


@payroll_bp.post("/runs/<int:rid>/revert")
@jwt_required()
@APPROVE
def run_revert(rid):
    """Batalkan pengajuan — kembalikan status ke 'draft'. Kalau sudah 'paid',
    balikkan efek kas (uang keluar dicatat balik masuk) & repayment kasbon
    yg sudah dipotong (dicatat sbg advance balik, bukan dihapus dr riwayat)."""
    r = db.session.get(PayrollRun, rid)
    if not r:
        return _err("Payroll tidak ditemukan", "not_found", 404)
    err = _check_venue(r)
    if err:
        return err
    if r.status == "draft":
        return _err("Payroll sudah berstatus draft", "bad_status", 409)
    uid = _user().id

    if r.status == "paid":
        for item in r.items:
            if _D(item.kasbon_deduction) > 0 and item.employee_id:
                db.session.add(EmployeeDebt(
                    employee_id=item.employee_id, type="advance", amount=_D(item.kasbon_deduction),
                    note=f"Pembatalan potong gaji {r.code}", created_by=uid,
                ))
        if r.source_account_id:
            from ..treasury.service import record_tx
            # balikkan nominal yg BENAR2 keluar (paid_amount, bisa beda dr total_net
            # kalau waktu bayar di-entry manual) — fallback total_net utk run lama
            reversed_amount = float(r.paid_amount) if r.paid_amount is not None else float(r.total_net)
            record_tx(
                r.source_account_id, "in", reversed_amount, "payroll_cancel",
                ref_type="payroll", ref_id=r.id, note=f"Pembatalan pembayaran {r.code}",
                user_id=uid,
            )
        r.paid_by = None
        r.paid_at = None
        r.paid_amount = None
        r.source_account_id = None

    r.status = "draft"
    r.approved_by = None
    r.approved_at = None
    r.rejection_reason = None
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(run=r.to_dict()), 200


@payroll_bp.delete("/runs/<int:rid>")
@jwt_required()
@CREATE
def run_delete(rid):
    """Hapus payroll run — hanya sebelum dibayar (blm ada efek kas).
    Run yg sudah 'paid' TIDAK bisa dihapus (akan merusak riwayat kas)."""
    r = db.session.get(PayrollRun, rid)
    if not r:
        return _err("Payroll tidak ditemukan", "not_found", 404)
    err = _check_venue(r)
    if err:
        return err
    if r.status not in ("draft", "submitted", "approved", "rejected"):
        return _err(
            f"Payroll sudah {r.status} — tidak bisa dihapus (sudah ada efek kas).",
            "bad_status", 409,
        )
    for att in r.attachments:
        path = os.path.join(_upload_dir(), att.stored_name)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(r)  # items & attachments (DB rows) ikut terhapus, ondelete=CASCADE
    db.session.commit()
    return jsonify(message="Payroll dihapus"), 200


# ------------------------------------------------------------------
# Lampiran (bukti transfer/dokumen)
# ------------------------------------------------------------------
def _upload_dir():
    d = os.path.join(current_app.config["UPLOAD_FOLDER"], "payroll")
    os.makedirs(d, exist_ok=True)
    return d


@payroll_bp.post("/runs/<int:rid>/attachment")
@jwt_required()
@CREATE
def run_attachment_upload(rid):
    r = db.session.get(PayrollRun, rid)
    if not r:
        return _err("Payroll tidak ditemukan", "not_found", 404)
    err = _check_venue(r)
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
    att = PayrollAttachment(
        run_id=rid, filename=secure_filename(f.filename), stored_name=stored,
        content_type=f.content_type, size_bytes=os.path.getsize(path),
    )
    db.session.add(att)
    db.session.commit()
    return jsonify(attachment=att.to_dict()), 201


@payroll_bp.get("/attachments/<int:aid>")
@jwt_required()
@VIEW
def run_attachment_get(aid):
    att = db.session.get(PayrollAttachment, aid)
    if not att:
        return _err("Lampiran tidak ditemukan", "not_found", 404)
    r = db.session.get(PayrollRun, att.run_id)
    err = _check_venue(r) if r else None
    if err:
        return err
    path = os.path.join(_upload_dir(), att.stored_name)
    if not os.path.exists(path):
        return _err("File hilang di server", "not_found", 404)
    return send_file(path, download_name=att.filename, mimetype=att.content_type)
