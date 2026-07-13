"""Laporan Keuangan (Financial Report) — agregasi lintas modul. Prefix: /api/financial

Modul TERAKHIR: menggabungkan penjualan POS + operasional + procurement + payroll
+ saldo kas menjadi Laba-Rugi & Arus Kas per venue.

Basis KAS (cash basis), konsisten dengan laporan penjualan:
- Pendapatan  = pembayaran yang DITERIMA dalam rentang (Payment.paid_at).
- Beban        = pengeluaran yang sudah CAIR/DIBAYAR dalam rentang:
    * Operasional  → OpRequest status=disbursed (disbursed_at), rincian per kategori.
    * Procurement  → PurchaseOrder status=paid (paid_at).
    * Payroll      → PayrollRun status=paid (paid_at), total_net.
- Saldo Kas   = snapshot saldo rekening saat ini (dari treasury), bukan periodik.

Akses: admin & head_office (semua venue); manager_unit (dibatasi ke venue-nya).
"""
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import User, Venue
from ..security import ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, roles_required
from ..pos.models import Order, Payment
from ..ops.models import ExpenseCategory, OpRequest, OpRequestItem
from ..proc.models import PurchaseOrder
from ..payroll.models import PayrollRun
from ..treasury.models import BankAccount
from ..treasury.service import account_balance

financial_bp = Blueprint("financial", __name__)

VIEW = roles_required(ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER)


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

    expense_total = operational_total + procurement_total + payroll_total
    net_profit = round(revenue_total - expense_total, 2)

    expense_breakdown = [
        {"group": "Operasional", "amount": round(operational_total, 2)},
        {"group": "Procurement", "amount": round(procurement_total, 2)},
        {"group": "Payroll", "amount": round(payroll_total, 2)},
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
