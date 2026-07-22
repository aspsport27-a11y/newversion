"""Kas & Bank — rekening, buku besar, setoran cash, rekonsiliasi QRIS, transfer.
Prefix: /api/treasury. Akses: admin & head_office."""
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import User, Venue
from ..pos.models import Order, Payment, Shift
from ..security import ROLE_ADMIN, require_perm, roles_required
from .models import AccountTransaction, BankAccount, BankReconciliation, CashDeposit, QrisSettlement
from .service import account_balance, account_balance_asof, cash_ho_account, holding_account, record_tx

treasury_bp = Blueprint("treasury", __name__)
MANAGE = require_perm("treasury.manage")  # RBAC configurable
ADMIN_ONLY = roles_required(ROLE_ADMIN)  # rekonsiliasi bank & penyesuaian jurnal — hard restricted admin saja


def _err(msg, code="bad_request", status=400):
    return jsonify(error=code, message=msg), status


def _uid():
    return int(get_jwt_identity())


def _D(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------
# Rekening
# ------------------------------------------------------------------
@treasury_bp.get("/accounts")
@jwt_required()
@MANAGE
def accounts_list():
    accs = BankAccount.query.order_by(BankAccount.type.desc(), BankAccount.name).all()
    rows = [a.to_dict(balance=account_balance(a.id)) for a in accs]
    return jsonify(accounts=rows, total_balance=round(sum(r["balance"] for r in rows), 2)), 200


@treasury_bp.post("/accounts")
@jwt_required()
@MANAGE
def accounts_create():
    d = request.get_json(silent=True) or {}
    if not d.get("name"):
        return _err("Nama rekening wajib")
    t = d.get("type", "venue")
    if t == "holding" and BankAccount.query.filter_by(type="holding").first():
        return _err("Rekening holding sudah ada", "duplicate", 409)
    if t == "cash_ho" and BankAccount.query.filter_by(type="cash_ho").first():
        return _err("Pool Kas Fisik HO sudah ada", "duplicate", 409)
    if t == "venue" and d.get("venue_id") and BankAccount.query.filter_by(type="venue", venue_id=d["venue_id"]).first():
        return _err("Venue ini sudah punya rekening", "duplicate", 409)
    a = BankAccount(
        name=d["name"], type=t, venue_id=(d.get("venue_id") if t == "venue" else None),
        bank_name=d.get("bank_name"), account_number=d.get("account_number"),
        opening_balance=_D(d.get("opening_balance")), is_active=True,
    )
    db.session.add(a)
    db.session.commit()
    return jsonify(account=a.to_dict(balance=account_balance(a.id))), 201


@treasury_bp.put("/accounts/<int:aid>")
@jwt_required()
@MANAGE
def accounts_update(aid):
    a = db.session.get(BankAccount, aid)
    if not a:
        return _err("Rekening tidak ditemukan", "not_found", 404)
    d = request.get_json(silent=True) or {}
    for f in ("name", "bank_name", "account_number"):
        if f in d:
            setattr(a, f, d[f])
    if "opening_balance" in d:
        a.opening_balance = _D(d["opening_balance"])
    if "is_active" in d:
        a.is_active = bool(d["is_active"])
    a.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(account=a.to_dict(balance=account_balance(a.id))), 200


@treasury_bp.get("/accounts/<int:aid>/ledger")
@jwt_required()
@MANAGE
def account_ledger(aid):
    a = db.session.get(BankAccount, aid)
    if not a:
        return _err("Rekening tidak ditemukan", "not_found", 404)
    q = AccountTransaction.query.filter_by(account_id=aid)
    f, t = request.args.get("from"), request.args.get("to")
    if f:
        q = q.filter(AccountTransaction.tx_date >= f)
    if t:
        q = q.filter(AccountTransaction.tx_date <= t)
    txs = q.order_by(AccountTransaction.tx_date.desc(), AccountTransaction.id.desc()).limit(500).all()
    total_in = round(sum(float(x.amount) for x in txs if x.direction == "in"), 2)
    total_out = round(sum(float(x.amount) for x in txs if x.direction == "out"), 2)
    return jsonify(
        account=a.to_dict(balance=account_balance(aid)),
        transactions=[x.to_dict() for x in txs],
        total_in=total_in, total_out=total_out,
    ), 200


# ------------------------------------------------------------------
# Transfer (sapu) & penyesuaian
# ------------------------------------------------------------------
@treasury_bp.post("/transfer")
@jwt_required()
@MANAGE
def transfer():
    d = request.get_json(silent=True) or {}
    src, dst = d.get("from_account_id"), d.get("to_account_id")
    amt = _D(d.get("amount"))
    if not src or not dst or src == dst or amt <= 0:
        return _err("from/to/amount tidak valid")
    if amt > account_balance(src):
        return _err("Saldo rekening asal tidak cukup", "insufficient", 409)
    note = d.get("note") or "Transfer/sapu"
    record_tx(src, "out", amt, "transfer_out", "sweep", dst, note, _uid())
    record_tx(dst, "in", amt, "transfer_in", "sweep", src, note, _uid())
    db.session.commit()
    return jsonify(message="Transfer tercatat"), 201


@treasury_bp.post("/adjust")
@jwt_required()
@ADMIN_ONLY
def adjust():
    """Penyesuaian jurnal manual — HANYA admin (bisa mengubah saldo rekening
    langsung, jadi dibatasi lebih ketat dari treasury.manage biasa)."""
    d = request.get_json(silent=True) or {}
    aid = d.get("account_id")
    direction = d.get("direction")
    amt = _D(d.get("amount"))
    if not aid or direction not in ("in", "out") or amt <= 0:
        return _err("account/direction/amount tidak valid")
    record_tx(aid, direction, amt, "adjustment", "manual", None, d.get("note"), _uid())
    db.session.commit()
    return jsonify(message="Penyesuaian tercatat"), 201


# ------------------------------------------------------------------
# Rekonsiliasi Bank (saldo sistem vs rekening koran) — ADMIN ONLY
# ------------------------------------------------------------------
@treasury_bp.get("/reconciliations")
@jwt_required()
@ADMIN_ONLY
def reconciliations_list():
    q = BankReconciliation.query
    aid = request.args.get("account_id", type=int)
    if aid:
        q = q.filter_by(account_id=aid)
    if request.args.get("status"):
        q = q.filter_by(status=request.args.get("status"))
    rows = q.order_by(BankReconciliation.period_to.desc(), BankReconciliation.id.desc()).limit(100).all()
    return jsonify(reconciliations=[x.to_dict() for x in rows]), 200


@treasury_bp.post("/reconciliations")
@jwt_required()
@ADMIN_ONLY
def reconciliations_create():
    """Bandingkan saldo sistem per tanggal tertentu vs saldo rekening koran
    (input manual dari mutasi bank). Selisih dicatat, bisa diselesaikan lewat
    penyesuaian jurnal (/treasury/adjust) lalu ditandai 'resolved'."""
    d = request.get_json(silent=True) or {}
    aid = d.get("account_id")
    period_to = d.get("period_to")
    statement_balance = _D(d.get("statement_balance"))
    if not aid or not period_to:
        return _err("account_id & period_to wajib")
    acc = db.session.get(BankAccount, aid)
    if not acc:
        return _err("Rekening tidak ditemukan", "not_found", 404)
    system_balance = account_balance_asof(aid, period_to)
    diff = round(statement_balance - system_balance, 2)
    rec = BankReconciliation(
        account_id=aid, period_to=period_to, statement_balance=statement_balance,
        system_balance=system_balance, difference=diff, note=d.get("note"),
        status="open" if diff else "resolved", created_by=_uid(),
    )
    if rec.status == "resolved":
        rec.resolved_by = _uid()
        rec.resolved_at = datetime.utcnow()
    db.session.add(rec)
    db.session.commit()
    return jsonify(reconciliation=rec.to_dict()), 201


@treasury_bp.post("/reconciliations/<int:rid>/resolve")
@jwt_required()
@ADMIN_ONLY
def reconciliations_resolve(rid):
    """Tandai selisih selesai — dipakai setelah penyesuaian jurnal diposting
    lewat /treasury/adjust (atau selisih ternyata cuma beda pencatatan)."""
    rec = db.session.get(BankReconciliation, rid)
    if not rec:
        return _err("Rekonsiliasi tidak ditemukan", "not_found", 404)
    if rec.status == "resolved":
        return _err("Sudah diselesaikan", "bad_status", 409)
    rec.status = "resolved"
    rec.resolved_by = _uid()
    rec.resolved_at = datetime.utcnow()
    d = request.get_json(silent=True) or {}
    if d.get("note"):
        rec.note = ((rec.note + "\n") if rec.note else "") + d["note"]
    db.session.commit()
    return jsonify(reconciliation=rec.to_dict()), 200


@treasury_bp.delete("/reconciliations/<int:rid>")
@jwt_required()
@ADMIN_ONLY
def reconciliations_delete(rid):
    rec = db.session.get(BankReconciliation, rid)
    if not rec:
        return _err("Rekonsiliasi tidak ditemukan", "not_found", 404)
    db.session.delete(rec)
    db.session.commit()
    return jsonify(message="Rekonsiliasi dihapus"), 200


# ------------------------------------------------------------------
# Setoran cash (gabungan shift → Kas Fisik HO)
# ------------------------------------------------------------------
@treasury_bp.get("/setoran/pending")
@jwt_required()
@MANAGE
def setoran_pending():
    shifts = Shift.query.filter(Shift.status == "closed", Shift.deposit_id.is_(None)).all()
    expected = sum(float(s.deposit_amount or 0) for s in shifts)
    rows = [{
        "id": s.id, "venue_id": s.venue_id,
        "deposit_amount": float(s.deposit_amount or 0),
        "closed_at": s.closed_at.isoformat() if s.closed_at else None,
    } for s in shifts]
    return jsonify(count=len(rows), expected_amount=round(expected, 2), shifts=rows), 200


@treasury_bp.post("/setoran")
@jwt_required()
@MANAGE
def setoran_create():
    """Kas dari shift yang ditutup unit-unit dikumpulkan HO, dihitung fisik,
    lalu dicatat masuk ke pool "Kas Fisik HO" (bukan langsung ke holding) —
    supaya bisa dipakai opex dulu sebelum disetor final via /setoran-holding.
    to_account_id masih bisa dioverride manual (mis. venue yang setor
    langsung ke bank sendiri, tanpa lewat pool HO)."""
    d = request.get_json(silent=True) or {}
    pool = cash_ho_account()
    to_acc = d.get("to_account_id") or (pool.id if pool else None)
    if not to_acc:
        return _err("Pool Kas Fisik HO belum dibuat", "no_cash_ho", 409)
    shifts = Shift.query.filter(Shift.status == "closed", Shift.deposit_id.is_(None)).all()
    if not shifts:
        return _err("Tidak ada shift yang perlu disetor")
    expected = round(sum(float(s.deposit_amount or 0) for s in shifts), 2)
    counted = _D(d.get("counted_amount"))
    code = f"SETOR-{date.today():%Y%m%d}-{(CashDeposit.query.count() + 1):03d}"
    dep = CashDeposit(
        code=code, to_account_id=to_acc, expected_amount=expected, counted_amount=counted,
        variance=round(counted - expected, 2), note=d.get("note"), created_by=_uid(),
    )
    db.session.add(dep)
    db.session.flush()
    for s in shifts:
        s.deposit_id = dep.id
    record_tx(to_acc, "in", counted, "cash_deposit", "setoran", dep.id, f"Setoran {code}", _uid())
    db.session.commit()
    return jsonify(deposit=dep.to_dict()), 201


@treasury_bp.get("/setoran")
@jwt_required()
@MANAGE
def setoran_list():
    q = CashDeposit.query
    f, t = request.args.get("from"), request.args.get("to")
    if f:
        q = q.filter(CashDeposit.deposit_date >= f)
    if t:
        q = q.filter(CashDeposit.deposit_date <= t)
    deps = q.order_by(CashDeposit.created_at.desc()).limit(100).all()
    return jsonify(deposits=[x.to_dict() for x in deps]), 200


# ------------------------------------------------------------------
# Setoran final (Kas Fisik HO → rekening Holding)
# ------------------------------------------------------------------
@treasury_bp.get("/setoran-holding/pending")
@jwt_required()
@MANAGE
def setoran_holding_pending():
    """Saldo Kas Fisik HO saat ini — bagian yang belum dipakai opex, siap
    disetor final ke rekening holding."""
    pool = cash_ho_account()
    if not pool:
        return _err("Pool Kas Fisik HO belum dibuat", "no_cash_ho", 409)
    return jsonify(account_id=pool.id, expected_amount=account_balance(pool.id)), 200


@treasury_bp.post("/setoran-holding")
@jwt_required()
@MANAGE
def setoran_holding_create():
    """Pindahkan sisa saldo Kas Fisik HO ke rekening holding — langkah
    terakhir setelah sebagian dipakai opex (payroll/procurement/operasional
    yang sumber dananya "Kas Fisik HO")."""
    d = request.get_json(silent=True) or {}
    pool = cash_ho_account()
    holding = holding_account()
    if not pool:
        return _err("Pool Kas Fisik HO belum dibuat", "no_cash_ho", 409)
    if not holding:
        return _err("Rekening holding belum dibuat", "no_holding", 409)
    expected = account_balance(pool.id)
    if expected <= 0:
        return _err("Saldo Kas Fisik HO kosong, tidak ada yang perlu disetor")
    counted = _D(d.get("counted_amount"))
    code = f"SETOR-HO-{date.today():%Y%m%d}-{(CashDeposit.query.count() + 1):03d}"
    dep = CashDeposit(
        code=code, from_account_id=pool.id, to_account_id=holding.id,
        expected_amount=expected, counted_amount=counted,
        variance=round(counted - expected, 2), note=d.get("note"), created_by=_uid(),
    )
    db.session.add(dep)
    db.session.flush()
    record_tx(pool.id, "out", counted, "cash_deposit_out", "setoran_holding", dep.id, f"Setoran {code}", _uid())
    record_tx(holding.id, "in", counted, "cash_deposit", "setoran_holding", dep.id, f"Setoran {code}", _uid())
    db.session.commit()
    return jsonify(deposit=dep.to_dict()), 201


# ------------------------------------------------------------------
# Rekonsiliasi QRIS (POS vs bank venue)
# ------------------------------------------------------------------
def _pos_qris_amount(venue_id, from_date, to_date):
    q = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.method == "qris", Payment.status == "paid", Order.venue_id == venue_id)
        .filter(func.date(Payment.paid_at).between(from_date, to_date))
    )
    return float(q.scalar() or 0)


@treasury_bp.get("/qris/pos-amount")
@jwt_required()
@MANAGE
def qris_pos_amount():
    vid = request.args.get("venue_id", type=int)
    f = request.args.get("from")
    t = request.args.get("to")
    if not vid or not f or not t:
        return _err("venue_id, from, to wajib")
    return jsonify(venue_id=vid, system_amount=_pos_qris_amount(vid, f, t)), 200


@treasury_bp.get("/qris")
@jwt_required()
@MANAGE
def qris_list():
    q = QrisSettlement.query
    f, t = request.args.get("from"), request.args.get("to")
    if f:
        q = q.filter(QrisSettlement.from_date >= f)
    if t:
        q = q.filter(QrisSettlement.to_date <= t)
    items = q.order_by(QrisSettlement.created_at.desc()).limit(100).all()
    return jsonify(settlements=[x.to_dict() for x in items]), 200


@treasury_bp.post("/qris")
@jwt_required()
@MANAGE
def qris_create():
    d = request.get_json(silent=True) or {}
    vid, f, t = d.get("venue_id"), d.get("from_date"), d.get("to_date")
    if not vid or not f or not t:
        return _err("venue_id, from_date, to_date wajib")
    from .service import venue_account
    acc = venue_account(vid)
    s = QrisSettlement(
        venue_id=vid, account_id=(acc.id if acc else None), from_date=f, to_date=t,
        system_amount=_pos_qris_amount(vid, f, t), actual_amount=_D(d.get("actual_amount")),
        status="draft", created_by=_uid(),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(settlement=s.to_dict()), 201


@treasury_bp.post("/qris/<int:sid>/approve")
@jwt_required()
@MANAGE
def qris_approve(sid):
    s = db.session.get(QrisSettlement, sid)
    if not s:
        return _err("Rekonsiliasi tidak ditemukan", "not_found", 404)
    if s.status != "draft":
        return _err("Sudah diproses", "bad_status", 409)
    if not s.account_id:
        return _err("Rekening venue belum dibuat", "no_account", 409)
    s.status = "approved"
    s.approved_by = _uid()
    s.approved_at = datetime.utcnow()
    # dana QRIS masuk ke rekening venue (nominal aktual yang masuk bank)
    record_tx(s.account_id, "in", float(s.actual_amount), "qris_in", "qris", s.id, f"QRIS {s.from_date}..{s.to_date}", _uid())
    db.session.commit()
    return jsonify(settlement=s.to_dict()), 200
