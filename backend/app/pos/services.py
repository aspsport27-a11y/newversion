"""Logika bisnis POS: order, pembayaran (provider), shift, stok."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func

from ..extensions import db
from ..models import Venue
from .models import (
    CashMovement,
    Order,
    OrderItem,
    Payment,
    Product,
    Shift,
    StockMovement,
)

VALID_ITEM_TYPES = {"product", "ticket", "rental", "booking"}
VALID_METHODS = {"cash", "qris"}


class PosError(Exception):
    """Error bisnis POS dengan kode & status HTTP."""

    def __init__(self, message, code="pos_error", status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def _D(v) -> Decimal:
    return Decimal(str(v or 0))


# ------------------------------------------------------------------
# Order number: {venue_code}-{YYYYMMDD}-{seq4}
# ------------------------------------------------------------------
def generate_order_number(venue: Venue) -> str:
    today = date.today()
    prefix = f"{venue.code}-{today:%Y%m%d}-"
    # hitung dari prefix order_number (robust, tak tergantung created_at)
    count = (
        db.session.query(func.count(Order.id))
        .filter(Order.order_number.like(prefix + "%"))
        .scalar()
        or 0
    )
    return f"{prefix}{count + 1:04d}"


# ------------------------------------------------------------------
# Buat order (status open) + item; hitung total. Stok belum dikurangi.
# ------------------------------------------------------------------
def create_order(shift: Shift, cashier_id: int, data: dict) -> Order:
    items_in = data.get("items") or []
    if not items_in:
        raise PosError("Order tidak boleh kosong", "empty_order")

    venue = db.session.get(Venue, shift.venue_id)
    order = Order(
        order_number=generate_order_number(venue),
        venue_id=shift.venue_id,
        terminal_id=shift.terminal_id,
        shift_id=shift.id,
        cashier_id=cashier_id,
        customer_name=(data.get("customer_name") or None),
        customer_phone=(data.get("customer_phone") or None),
        status="open",
    )

    subtotal = Decimal("0")
    for row in items_in:
        item_type = row.get("item_type", "product")
        if item_type not in VALID_ITEM_TYPES:
            raise PosError(f"item_type tidak valid: {item_type}", "bad_item_type")
        qty = _D(row.get("quantity", 1))
        if qty <= 0:
            raise PosError("Quantity harus > 0", "bad_quantity")

        if item_type == "product":
            product = db.session.get(Product, row.get("product_id"))
            if product is None or not product.is_active:
                raise PosError("Produk tidak ditemukan/nonaktif", "product_not_found", 404)
            if product.venue_id != shift.venue_id:
                raise PosError("Produk bukan milik venue ini", "product_wrong_venue")
            if product.track_stock and product.stock_qty < qty:
                raise PosError(
                    f"Stok '{product.name}' kurang (sisa {product.stock_qty})",
                    "insufficient_stock",
                )
            name = product.name
            unit_price = _D(product.price)
            product_id = product.id
        else:
            # ticket/rental/booking: nama & harga dari input (booking dari M2)
            name = row.get("name") or item_type
            unit_price = _D(row.get("unit_price"))
            product_id = row.get("product_id")

        line_total = (unit_price * qty).quantize(Decimal("0.01"))
        subtotal += line_total
        order.items.append(
            OrderItem(
                item_type=item_type,
                product_id=product_id,
                name_snapshot=name[:120],
                unit_price=unit_price,
                quantity=qty,
                line_total=line_total,
            )
        )

    discount = _D(data.get("discount_amount"))
    if discount < 0 or discount > subtotal:
        raise PosError("Diskon tidak valid", "bad_discount")
    order.subtotal = subtotal
    order.discount_amount = discount
    order.total_amount = subtotal - discount

    db.session.add(order)
    db.session.flush()
    return order


# ------------------------------------------------------------------
# Provider pembayaran (colok-lepas). M1: cash aktif; qris_bri stub.
# ------------------------------------------------------------------
def _pay_cash(order, payment, **_):
    payment.status = "paid"
    payment.paid_at = datetime.utcnow()


def _pay_qris_bri(order, payment, **_):
    # M3: integrasi BRIAPI MPM Dinamis (generate QR) + Notifikasi (webhook konfirmasi).
    # Untuk sekarang: buat transaksi 'pending' — dikonfirmasi via webhook/endpoint terpisah.
    payment.status = "pending"


PROVIDERS = {
    "cash": _pay_cash,
    "bri_qris_mpm": _pay_qris_bri,
}


def pay_order(order: Order, cashier_id: int, data: dict) -> Payment:
    if order.status != "open":
        raise PosError("Order sudah tidak bisa dibayar", "order_not_open")

    method = data.get("method")
    if method not in VALID_METHODS:
        raise PosError("Metode bayar tidak valid (cash|qris)", "bad_method")
    provider = data.get("provider") or ("cash" if method == "cash" else "bri_qris_mpm")
    if provider not in PROVIDERS:
        raise PosError(f"Provider tidak dikenal: {provider}", "bad_provider")

    payment = Payment(
        order_id=order.id,
        method=method,
        provider=provider,
        amount=order.total_amount,
        status="pending",
        reference=(data.get("reference") or None),
        confirmed_by=cashier_id,
    )
    db.session.add(payment)

    PROVIDERS[provider](order, payment, data=data)

    if payment.status == "paid":
        _finalize_paid(order, payment, cashier_id)

    db.session.commit()
    return payment


def _finalize_paid(order: Order, payment: Payment, cashier_id: int) -> None:
    """Order lunas: kurangi stok + update total shift."""
    order.status = "paid"
    order.updated_at = datetime.utcnow()

    # kurangi stok produk yang dilacak
    for item in order.items:
        if item.item_type == "product" and item.product_id:
            product = db.session.get(Product, item.product_id)
            if product and product.track_stock:
                qty = int(item.quantity)
                product.stock_qty -= qty
                db.session.add(
                    StockMovement(
                        product_id=product.id,
                        venue_id=order.venue_id,
                        type="sale",
                        quantity=-qty,
                        balance_after=product.stock_qty,
                        reference=order.order_number,
                        created_by=cashier_id,
                    )
                )

    # update akumulasi shift
    shift = db.session.get(Shift, order.shift_id)
    if shift:
        amt = order.total_amount
        shift.total_sales = _D(shift.total_sales) + amt
        if payment.method == "cash":
            shift.total_cash_sales = _D(shift.total_cash_sales) + amt
        elif payment.method == "qris":
            shift.total_qris_sales = _D(shift.total_qris_sales) + amt


# ------------------------------------------------------------------
# Shift
# ------------------------------------------------------------------
def open_shift(terminal_id, venue_id, cashier_id, opening_cash) -> Shift:
    existing = Shift.query.filter_by(terminal_id=terminal_id, status="open").first()
    if existing:
        raise PosError("Masih ada shift terbuka di terminal ini", "shift_already_open", 409)
    shift = Shift(
        terminal_id=terminal_id,
        venue_id=venue_id,
        cashier_id=cashier_id,
        status="open",
        opened_at=datetime.utcnow(),
        opening_cash=_D(opening_cash),
    )
    db.session.add(shift)
    db.session.commit()
    return shift


def add_cash_movement(shift: Shift, mtype, amount, reason, user_id) -> CashMovement:
    if shift.status != "open":
        raise PosError("Shift sudah ditutup", "shift_closed")
    if mtype not in ("in", "out"):
        raise PosError("type harus in|out", "bad_type")
    amount = _D(amount)
    mv = CashMovement(
        shift_id=shift.id, type=mtype, amount=amount, reason=reason, created_by=user_id
    )
    if mtype == "in":
        shift.cash_in = _D(shift.cash_in) + amount
    else:
        shift.cash_out = _D(shift.cash_out) + amount
    db.session.add(mv)
    db.session.commit()
    return mv


def close_shift(shift: Shift, counted_cash, deposit_amount=None, notes=None) -> Shift:
    if shift.status != "open":
        raise PosError("Shift sudah ditutup", "shift_closed")
    expected = (
        _D(shift.opening_cash)
        + _D(shift.total_cash_sales)
        + _D(shift.cash_in)
        - _D(shift.cash_out)
    )
    counted = _D(counted_cash)
    shift.expected_cash = expected
    shift.counted_cash = counted
    shift.cash_variance = counted - expected
    shift.deposit_amount = _D(deposit_amount) if deposit_amount is not None else None
    shift.notes = notes
    shift.status = "closed"
    shift.closed_at = datetime.utcnow()
    db.session.commit()
    return shift
