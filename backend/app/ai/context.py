"""Ringkasan keadaan bisnis TERKINI untuk disuntik ke Ask AI ("melek data").
Dibuat ringkas (hemat token) tapi cukup untuk tanya-jawab operasional. Selalu
hormati scope user (manager → venue-nya). Untuk data historis spesifik di luar
ringkasan ini, Ask AI mengarahkan ke menu Laporan (dijelaskan di system prompt)."""
from datetime import date, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import Venue
from ..ops.models import OpRequest
from ..payroll.models import PayrollRun
from ..pos.models import Order, Payment, Product
from ..proc.models import PurchaseOrder
from ..treasury.models import BankAccount


def _rp(n):
    return "Rp " + f"{int(round(n or 0)):,}".replace(",", ".")


def build_business_context(user):
    """Kembalikan blok teks ringkas keadaan bisnis terkini sesuai scope `user`,
    atau string kosong bila tak bisa dihitung."""
    # impor di dalam fungsi utk hindari circular import (admin.routes berat)
    from ..admin.routes import _radar_findings, _sales_growth_mom, _scope_vids
    from ..treasury.service import account_balance

    vids = _scope_vids(user)

    def scoped(q, model):
        if vids is None:
            return q
        if not vids:
            return q.filter(db.false())
        return q.filter(model.venue_id.in_(vids))

    today = date.today()
    yesterday = today - timedelta(days=1)

    rev_today = float(scoped(
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.status == "paid", func.date(Payment.paid_at) == today), Order,
    ).scalar() or 0)
    rev_yst = float(scoped(
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.status == "paid", func.date(Payment.paid_at) == yesterday), Order,
    ).scalar() or 0)
    orders_today = scoped(
        Order.query.filter(Order.status == "paid", func.date(Order.created_at) == today), Order,
    ).count()

    ops_p = scoped(OpRequest.query.filter_by(status="submitted"), OpRequest).count()
    pay_p = scoped(PayrollRun.query.filter_by(status="submitted"), PayrollRun).count()
    proc_p = scoped(PurchaseOrder.query.filter_by(status="submitted"), PurchaseOrder).count()

    low_stock = scoped(
        Product.query.filter(
            Product.is_active.is_(True), Product.track_stock.is_(True),
            Product.stock_qty <= Product.min_stock,
        ), Product,
    ).count()

    findings = _radar_findings(vids)

    # deskripsi scope biar AI paham cakupan angka ini
    if vids is None:
        scope = "SEMUA venue"
    elif not vids:
        scope = "tidak ada venue (belum di-set)"
    else:
        codes = [v.code for v in Venue.query.filter(Venue.id.in_(vids)).all()]
        scope = "venue: " + ", ".join(codes)

    lines = [
        f"RINGKASAN DATA TERKINI (per {today.isoformat()}, cakupan {scope}):",
        f"- Omzet hari ini: {_rp(rev_today)} (kemarin: {_rp(rev_yst)})",
        f"- Transaksi lunas hari ini: {orders_today}",
        f"- Approval menunggu: operasional {ops_p}, payroll {pay_p}, procurement {proc_p}",
        f"- Produk stok menipis: {low_stock}",
    ]

    # --- Omzet & pertumbuhan bulan ini per venue (dari data Dashboard) ---
    try:
        mom = _sales_growth_mom(vids)
        active = [v for v in mom["venues"] if v["this_month"] or v["last_month"]]
        if active:
            lines.append(
                f"- Omzet bulan ini per venue ({mom['this_month_range']['from']}..{mom['this_month_range']['to']}, "
                "vs periode sama bulan lalu):"
            )
            for v in sorted(active, key=lambda x: x["this_month"], reverse=True):
                if v["is_new"]:
                    g = "baru"
                elif v["growth_pct"] is None:
                    g = "—"
                else:
                    g = f"{'+' if v['growth_pct'] >= 0 else ''}{v['growth_pct']}%"
                lines.append(f"  • {v['venue_name']}: {_rp(v['this_month'])} ({g})")
    except Exception:
        pass

    # --- Saldo kas per rekening + piutang (Kas & Bank) ---
    try:
        acc_q = BankAccount.query
        if vids is not None:
            acc_q = acc_q.filter(BankAccount.venue_id.in_(vids)) if vids else acc_q.filter(db.false())
        accounts = acc_q.all()
        if accounts:
            total_cash = 0.0
            bal_lines = []
            for a in accounts:
                b = account_balance(a.id)
                total_cash += b
                bal_lines.append(f"  • {a.name}: {_rp(b)}")
            lines.append(f"- Saldo kas/rekening (total {_rp(total_cash)}):")
            lines.extend(bal_lines)
    except Exception:
        pass

    try:
        oq = Order.query.filter(Order.status == "partial")
        if vids is not None:
            oq = oq.filter(Order.venue_id.in_(vids)) if vids else oq.filter(db.false())
        due = 0.0
        cnt = 0
        for o in oq.all():
            due += float(o.total_amount or 0) - float(o.amount_paid or 0)
            cnt += 1
        if cnt:
            lines.append(f"- Piutang (DP belum lunas): {_rp(due)} dari {cnt} booking")
        else:
            lines.append("- Piutang: tidak ada")
    except Exception:
        pass

    if findings:
        lines.append(f"- Radar Operasional — {len(findings)} hal perlu dicek (urut prioritas):")
        for i, f in enumerate(findings[:10], 1):
            lines.append(f"  {i}. {f['title']} — {f['detail']}")
    else:
        lines.append("- Radar Operasional: aman, tidak ada yang perlu dicek.")

    return "\n".join(lines)
