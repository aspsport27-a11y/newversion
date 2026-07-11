"""Engine promo: resolve promo aktif + hitung harga/line dengan promo.

Tipe promo:
- price   : harga promo tetap (promo_price)
- percent : diskon persen (percent, mis. 20 = 20%)
- bogo    : beli buy_qty gratis get_qty
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import or_

from ..extensions import db
from .models import Promo


def active_promo(product_id, on=None):
    """Promo aktif untuk produk pada tanggal `on` (default hari ini)."""
    on = on or date.today()
    return (
        Promo.query.filter(
            Promo.product_id == product_id,
            Promo.is_active.is_(True),
            or_(Promo.start_date.is_(None), Promo.start_date <= on),
            or_(Promo.end_date.is_(None), Promo.end_date >= on),
        )
        .order_by(Promo.id)
        .first()
    )


def promo_label(p) -> str:
    if p is None:
        return ""
    if p.type == "price" and p.promo_price is not None:
        return f"Promo Rp{int(p.promo_price):,}".replace(",", ".")
    if p.type == "percent" and p.percent is not None:
        return f"Diskon {int(p.percent)}%"
    if p.type == "bogo" and p.buy_qty and p.get_qty:
        return f"Beli {p.buy_qty} Gratis {p.get_qty}"
    return p.name or "Promo"


def effective_unit_price(product, promo) -> float:
    """Harga satuan setelah promo price/percent (bogo tak ubah harga satuan)."""
    price = float(product.price or 0)
    if promo is None:
        return price
    if promo.type == "price" and promo.promo_price is not None:
        pp = float(promo.promo_price)
        return pp if 0 < pp < price else price
    if promo.type == "percent" and promo.percent is not None:
        return round(price * (1 - float(promo.percent) / 100.0), 2)
    return price


def compute_line(product, qty, promo):
    """Kembalikan (unit_price, line_total) untuk qty item dengan promo.

    price/percent → harga satuan turun. bogo → sebagian gratis (qty tetap,
    yang dibayar berkurang).
    """
    qty = Decimal(str(qty))
    unit = Decimal(str(effective_unit_price(product, promo)))
    paid_qty = qty
    if promo is not None and promo.type == "bogo" and promo.buy_qty and promo.get_qty:
        group = promo.buy_qty + promo.get_qty
        free = (int(qty) // group) * promo.get_qty
        paid_qty = qty - Decimal(free)
    line_total = (unit * paid_qty).quantize(Decimal("0.01"))
    return unit, line_total


def product_public(product) -> dict:
    """dict produk + promo aktif + harga efektif (untuk POS & admin)."""
    d = product.to_dict()
    promo = active_promo(product.id)
    d["effective_price"] = effective_unit_price(product, promo)
    if promo is not None:
        d["promo"] = {
            "type": promo.type,
            "label": promo_label(promo),
            "buy_qty": promo.buy_qty,
            "get_qty": promo.get_qty,
        }
    else:
        d["promo"] = None
    return d
