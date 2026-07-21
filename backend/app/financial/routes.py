"""Laporan Keuangan (Financial Report) — agregasi lintas modul. Prefix: /api/financial

Modul TERAKHIR: menggabungkan penjualan POS + operasional + procurement + payroll
+ saldo kas menjadi Laba-Rugi & Arus Kas per venue.

Basis KAS (cash basis), konsisten dengan laporan penjualan:
- Pendapatan  = pembayaran yang DITERIMA dalam rentang (Payment.paid_at).
- Beban        = pengeluaran yang sudah CAIR/DIBAYAR dalam rentang:
    * Operasional  → OpRequest status=disbursed (disbursed_at), rincian per kategori.
    * Procurement  → PurchaseOrder status=paid (paid_at).
    * Payroll      → PayrollRun status=paid (paid_at), total_net.
    * Konsinyasi   → ConsignmentSettlement paid_at terisi, total_amount (bagi hasil
      ke supplier titipan — pendapatan penjualannya sudah masuk penuh/gross di atas,
      jadi ini WAJIB dihitung sbg beban biar laba bersih tidak overstated).
- Saldo Kas   = snapshot saldo rekening saat ini (dari treasury), bukan periodik.

Akses: admin & head_office (semua venue); manager_unit (dibatasi ke venue-nya).
"""
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import User, Venue
from ..security import ROLE_MANAGER, require_perm
from ..pos.models import Order, Payment
from ..ops.models import ExpenseCategory, OpRequest, OpRequestItem
from ..proc.models import ConsignmentSettlement, PurchaseOrder
from ..payroll.models import PayrollRun
from ..treasury.models import BankAccount
from ..treasury.service import account_balance, holding_account, record_tx
from .models import HOLDING_CATEGORIES, HoldingExpense

financial_bp = Blueprint("financial", __name__)

# RBAC configurable (izin dikelola via /admin/permissions)
VIEW = require_perm("report.business")
# data owner-sensitif — izin terpisah: lihat laporan vs kelola beban holding
MANAGE_REPORT = require_perm("report.management")
MANAGE_HOLDING = require_perm("holding.manage")


def _current_user():
    return db.session.get(User, int(get_jwt_identity()))


def _date_range():
    today = date.today().isoformat()
    return request.args.get("from") or today, request.args.get("to") or today


def _venue_filter():
    """Venue efektif: manager unit dipaksa ke venue-nya; lainnya ikut query ?venue_id."""
    u = _current_user()
    if u and u.role == ROLE_MANAGER:
        return u.venue_id
    return request.args.get("venue_id", type=int)


def _f(v):
    return float(v or 0)


@financial_bp.get("/report")
@jwt_required()
@VIEW
def report():
    d_from, d_to = _date_range()
    vid = _venue_filter()

    # ---------- PENDAPATAN (basis kas: pembayaran diterima) ----------
    pay_q = (
        db.session.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.status == "paid")
        .filter(func.date(Payment.paid_at).between(d_from, d_to))
    )
    if vid:
        pay_q = pay_q.filter(Order.venue_id == vid)

    revenue_total = _f(
        pay_q.with_entities(func.coalesce(func.sum(Payment.amount), 0)).scalar()
    )
    revenue_by_method = [
        {"method": m, "amount": _f(a)}
        for m, a in pay_q.with_entities(
            Payment.method, func.coalesce(func.sum(Payment.amount), 0)
        ).group_by(Payment.method).all()
    ]
    revenue_daily = {
        str(day): _f(a)
        for day, a in pay_q.with_entities(
            func.date(Payment.paid_at), func.coalesce(func.sum(Payment.amount), 0)
        ).group_by(func.date(Payment.paid_at)).all()
    }

    # ---------- BEBAN OPERASIONAL (disbursed, per kategori) ----------
    op_q = (
        db.session.query(
            OpRequestItem.category_id,
            func.coalesce(func.sum(OpRequestItem.amount), 0),
        )
        .join(OpRequest, OpRequestItem.request_id == OpRequest.id)
        .filter(OpRequest.status == "disbursed")
        .filter(func.date(OpRequest.disbursed_at).between(d_from, d_to))
    )
    if vid:
        op_q = op_q.filter(OpRequest.venue_id == vid)
    op_rows = op_q.group_by(OpRequestItem.category_id).all()
    cat_names = {c.id: c.name for c in ExpenseCategory.query.all()}
    operational_by_category = sorted(
        [
            {"category": cat_names.get(cid, f"#{cid}"), "amount": _f(a)}
            for cid, a in op_rows
        ],
        key=lambda r: r["amount"],
        reverse=True,
    )
    operational_total = sum(r["amount"] for r in operational_by_category)

    # ---------- BEBAN PROCUREMENT (PO dibayar) ----------
    po_q = PurchaseOrder.query.filter(
        PurchaseOrder.status == "paid",
        func.date(PurchaseOrder.paid_at).between(d_from, d_to),
    )
    if vid:
        po_q = po_q.filter(PurchaseOrder.venue_id == vid)
    procurement_total = _f(
        po_q.with_entities(
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0)
        ).scalar()
    )

    # ---------- BEBAN PAYROLL (gaji dibayar) ----------
    pr_q = PayrollRun.query.filter(
        PayrollRun.status == "paid",
        func.date(PayrollRun.paid_at).between(d_from, d_to),
    )
    if vid:
        pr_q = pr_q.filter(PayrollRun.venue_id == vid)
    payroll_total = _f(
        pr_q.with_entities(func.coalesce(func.sum(PayrollRun.total_net), 0)).scalar()
    )

    # ---------- BEBAN KONSINYASI (settlement bagi hasil sudah dibayar) ----------
    ksg_q = ConsignmentSettlement.query.filter(
        ConsignmentSettlement.paid_at.isnot(None),
        func.date(ConsignmentSettlement.paid_at).between(d_from, d_to),
    )
    if vid:
        ksg_q = ksg_q.filter(ConsignmentSettlement.venue_id == vid)
    consignment_total = _f(
        ksg_q.with_entities(func.coalesce(func.sum(ConsignmentSettlement.total_amount), 0)).scalar()
    )

    expense_total = operational_total + procurement_total + payroll_total + consignment_total
    net_profit = round(revenue_total - expense_total, 2)

    expense_breakdown = [
        {"group": "Operasional", "amount": round(operational_total, 2)},
        {"group": "Procurement", "amount": round(procurement_total, 2)},
        {"group": "Payroll", "amount": round(payroll_total, 2)},
        {"group": "Konsinyasi (bagi hasil)", "amount": round(consignment_total, 2)},
    ]

    # ---------- SALDO KAS (snapshot, bukan periodik) ----------
    acc_q = BankAccount.query.filter_by(is_active=True)
    if vid:
        # rekening venue tsb + rekening holding (uang bisa mengendap di holding)
        acc_q = acc_q.filter(
            (BankAccount.venue_id == vid) | (BankAccount.type == "holding")
        )
    accounts = []
    cash_total = 0.0
    for acc in acc_q.order_by(BankAccount.type.desc(), BankAccount.name).all():
        bal = account_balance(acc.id)
        cash_total += bal
        accounts.append({**acc.to_dict(balance=bal)})

    return jsonify(
        range={"from": d_from, "to": d_to},
        venue_id=vid,
        revenue={
            "total": round(revenue_total, 2),
            "by_method": revenue_by_method,
            "daily": revenue_daily,
        },
        expenses={
            "operational": round(operational_total, 2),
            "operational_by_category": operational_by_category,
            "procurement": round(procurement_total, 2),
            "payroll": round(payroll_total, 2),
            "consignment": round(consignment_total, 2),
            "total": round(expense_total, 2),
            "breakdown": expense_breakdown,
        },
        net_profit=net_profit,
        margin_pct=round(net_profit / revenue_total * 100, 1) if revenue_total else 0.0,
        cashflow={
            "in": round(revenue_total, 2),
            "out": round(expense_total, 2),
            "net": net_profit,
        },
        cash={"total": round(cash_total, 2), "accounts": accounts},
    ), 200


# =====================================================================
# BEBAN HOLDING / OWNER (sensitif — HANYA admin/head_office)
# =====================================================================

def _gen_holding_code():
    today = date.today()
    prefix = f"HLD-{today:%Y%m}-"
    last = (
        HoldingExpense.query.filter(HoldingExpense.code.like(prefix + "%"))
        .order_by(HoldingExpense.code.desc())
        .first()
    )
    seq = int(last.code.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:03d}"


@financial_bp.get("/holding-expenses")
@jwt_required()
@MANAGE_HOLDING
def holding_expenses_list():
    d_from, d_to = _date_range()
    # default: seluruh tahun berjalan bila tak diberi rentang eksplisit
    if not request.args.get("from"):
        d_from = f"{date.today().year}-01-01"
    q = HoldingExpense.query.filter(
        HoldingExpense.expense_date.between(d_from, d_to)
    ).order_by(HoldingExpense.expense_date.desc(), HoldingExpense.id.desc())
    rows = [e.to_dict() for e in q.all()]
    total = round(sum(r["amount"] for r in rows), 2)
    return jsonify(
        range={"from": d_from, "to": d_to},
        categories=HOLDING_CATEGORIES,
        total=total,
        expenses=rows,
    ), 200


@financial_bp.post("/holding-expenses")
@jwt_required()
@MANAGE_HOLDING
def holding_expenses_create():
    d = request.get_json(silent=True) or {}
    category = (d.get("category") or "").strip()
    amount = d.get("amount")
    if category not in HOLDING_CATEGORIES:
        return jsonify(error="bad_request", message="Kategori tidak valid"), 400
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return jsonify(error="bad_request", message="Nominal harus lebih dari 0"), 400

    # sumber dana: rekening holding (default) atau yang dipilih
    src_id = d.get("source_account_id")
    if src_id:
        acc = db.session.get(BankAccount, int(src_id))
    else:
        acc = holding_account()
    if not acc:
        return jsonify(error="bad_request", message="Rekening holding belum ada"), 400

    exp_date = d.get("expense_date")
    exp = HoldingExpense(
        code=_gen_holding_code(),
        category=category,
        description=(d.get("description") or "").strip() or None,
        amount=amount,
        source_account_id=acc.id,
        created_by=_current_user().id,
    )
    if exp_date:
        try:
            exp.expense_date = date.fromisoformat(exp_date)
        except ValueError:
            pass
    db.session.add(exp)
    db.session.flush()  # dapat id utk ref
    # uang keluar dari rekening holding → tampil di buku besar treasury
    record_tx(
        acc.id, "out", amount, "holding_expense",
        ref_type="holding_expense", ref_id=exp.id,
        note=f"{category}: {exp.description or ''}".strip(": ").strip(),
        user_id=exp.created_by, tx_date=exp.expense_date,
    )
    db.session.commit()
    return jsonify(expense=exp.to_dict()), 201


@financial_bp.delete("/holding-expenses/<int:eid>")
@jwt_required()
@MANAGE_HOLDING
def holding_expenses_delete(eid):
    exp = db.session.get(HoldingExpense, eid)
    if not exp:
        return jsonify(error="not_found", message="Data tidak ditemukan"), 404
    # hapus juga mutasi treasury terkait (balik saldo holding)
    from ..treasury.models import AccountTransaction
    AccountTransaction.query.filter_by(
        ref_type="holding_expense", ref_id=exp.id
    ).delete()
    db.session.delete(exp)
    db.session.commit()
    return jsonify(ok=True), 200


# =====================================================================
# LAPORAN MANAJEMEN (HO only) — konsolidasi semua venue + beban holding/owner
# =====================================================================

@financial_bp.get("/management-report")
@jwt_required()
@MANAGE_REPORT
def management_report():
    d_from, d_to = _date_range()

    # --- Pendapatan per venue (basis kas) ---
    rev_rows = dict(
        db.session.query(
            Order.venue_id, func.coalesce(func.sum(Payment.amount), 0)
        )
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.status == "paid")
        .filter(func.date(Payment.paid_at).between(d_from, d_to))
        .group_by(Order.venue_id)
        .all()
    )

    # --- Beban per venue: operasional (disbursed) ---
    op_rows = dict(
        db.session.query(
            OpRequest.venue_id, func.coalesce(func.sum(OpRequest.total_amount), 0)
        )
        .filter(OpRequest.status == "disbursed")
        .filter(func.date(OpRequest.disbursed_at).between(d_from, d_to))
        .group_by(OpRequest.venue_id)
        .all()
    )
    # --- procurement (paid) ---
    po_rows = dict(
        db.session.query(
            PurchaseOrder.venue_id,
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0),
        )
        .filter(PurchaseOrder.status == "paid")
        .filter(func.date(PurchaseOrder.paid_at).between(d_from, d_to))
        .group_by(PurchaseOrder.venue_id)
        .all()
    )
    # --- payroll (paid) ---
    pr_rows = dict(
        db.session.query(
            PayrollRun.venue_id, func.coalesce(func.sum(PayrollRun.total_net), 0)
        )
        .filter(PayrollRun.status == "paid")
        .filter(func.date(PayrollRun.paid_at).between(d_from, d_to))
        .group_by(PayrollRun.venue_id)
        .all()
    )
    # --- konsinyasi (settlement bagi hasil sudah dibayar) ---
    ksg_rows = dict(
        db.session.query(
            ConsignmentSettlement.venue_id,
            func.coalesce(func.sum(ConsignmentSettlement.total_amount), 0),
        )
        .filter(ConsignmentSettlement.paid_at.isnot(None))
        .filter(func.date(ConsignmentSettlement.paid_at).between(d_from, d_to))
        .group_by(ConsignmentSettlement.venue_id)
        .all()
    )

    venue_ids = set(rev_rows) | set(op_rows) | set(po_rows) | set(pr_rows) | set(ksg_rows)
    vnames = {
        v.id: {"code": v.code, "name": v.name}
        for v in Venue.query.filter(Venue.id.in_(venue_ids)).all()
    } if venue_ids else {}

    by_venue = []
    biz_revenue = biz_expense = 0.0
    for vid in venue_ids:
        rev = _f(rev_rows.get(vid))
        exp = _f(op_rows.get(vid)) + _f(po_rows.get(vid)) + _f(pr_rows.get(vid)) + _f(ksg_rows.get(vid))
        biz_revenue += rev
        biz_expense += exp
        info = vnames.get(vid, {})
        by_venue.append({
            "venue_id": vid,
            "venue_code": info.get("code"),
            "venue_name": info.get("name"),
            "revenue": round(rev, 2),
            "expense": round(exp, 2),
            "net": round(rev - exp, 2),
        })
    by_venue.sort(key=lambda r: r["net"], reverse=True)
    business_net = round(biz_revenue - biz_expense, 2)

    # --- Beban holding/owner (prive, fee direktur, bonus) ---
    hexp = HoldingExpense.query.filter(
        HoldingExpense.expense_date.between(d_from, d_to)
    ).all()
    holding_by_cat = {}
    for e in hexp:
        holding_by_cat[e.category] = holding_by_cat.get(e.category, 0) + _f(e.amount)
    holding_total = round(sum(holding_by_cat.values()), 2)
    holding_by_category = sorted(
        [{"category": k, "amount": round(v, 2)} for k, v in holding_by_cat.items()],
        key=lambda r: r["amount"], reverse=True,
    )

    net_true = round(business_net - holding_total, 2)

    # --- Saldo kas seluruh rekening (venue + holding) ---
    accounts, cash_total = [], 0.0
    for acc in BankAccount.query.filter_by(is_active=True).order_by(
        BankAccount.type.desc(), BankAccount.name
    ).all():
        bal = account_balance(acc.id)
        cash_total += bal
        accounts.append(acc.to_dict(balance=bal))

    return jsonify(
        range={"from": d_from, "to": d_to},
        business={
            "revenue": round(biz_revenue, 2),
            "expense": round(biz_expense, 2),
            "net": business_net,
            "by_venue": by_venue,
        },
        holding={"total": holding_total, "by_category": holding_by_category},
        net_profit=net_true,
        cash={"total": round(cash_total, 2), "accounts": accounts},
    ), 200

