"""Payroll — generate gaji (auto hitung + potong kasbon), approval, pembayaran.
Prefix: /api/payroll"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import Employee, EmployeeDebt, User, Venue
from ..security import ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, roles_required
from .models import PayrollItem, PayrollRun

payroll_bp = Blueprint("payroll", __name__)

VIEW = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)
CREATE = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)  # unit generate
APPROVE = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE)  # HO approve & pay


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
    """Bayar (transfer). Eksekusi potong kasbon → employee_debts repayment."""
    r, err = _transition(rid, "approved", "paid")
    if err:
        return err
    uid = _user().id
    src = (request.get_json(silent=True) or {}).get("source_account_id")
    if src:
        from ..treasury.service import pay_expense
        ok, perr = pay_expense(src, float(r.total_net), "payroll", r.id, f"Gaji {r.code}", uid)
        if perr:
            return _err(perr)
        r.source_account_id = src
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
