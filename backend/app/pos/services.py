"""Logika bisnis POS: order, pembayaran (provider), shift, stok."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func

from ..extensions import db
from ..models import Venue
from .models import (
    CashMovement,
    Facility,
    FacilityBooking,
    Order,
    OrderItem,
    Payment,
    Product,
    Shift,
    StockMovement,
)


def _parse_time(s):
    return datetime.strptime(s, "%H:%M").time()


def _hours_between(start, end) -> float:
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    return (e - s) / 60.0


def is_slot_available(facility_id, booking_date, start, end, exclude_id=None) -> bool:
    """True jika slot [start,end) di tanggal itu belum dibooking (tanpa overlap)."""
    q = FacilityBooking.query.filter(
        FacilityBooking.facility_id == facility_id,
        FacilityBooking.booking_date == booking_date,
        FacilityBooking.status == "booked",
        FacilityBooking.start_time < end,
        FacilityBooking.end_time > start,
    )
    if exclude_id:
        q = q.filter(FacilityBooking.id != exclude_id)
    return not db.session.query(q.exists()).scalar()

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
    booking_specs = []  # (order_item, facility_id, date, start, end)
    for row in items_in:
        item_type = row.get("item_type", "product")
        if item_type not in VALID_ITEM_TYPES:
            raise PosError(f"item_type tidak valid: {item_type}", "bad_item_type")

        if item_type == "product":
            qty = _D(row.get("quantity", 1))
            if qty <= 0:
                raise PosError("Quantity harus > 0", "bad_quantity")
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
            eff = _D(product.effective_price)  # harga promo bila ada
            oi = OrderItem(
                item_type="product", product_id=product.id, name_snapshot=product.name[:120],
                unit_price=eff, quantity=qty,
                line_total=(eff * qty).quantize(Decimal("0.01")),
            )

        elif item_type == "booking":
            facility = db.session.get(Facility, row.get("facility_id"))
            if facility is None or not facility.is_active or facility.venue_id != shift.venue_id:
                raise PosError("Lapangan tidak ditemukan/nonaktif", "facility_not_found", 404)
            try:
                bdate = date.fromisoformat(row["booking_date"])
                start = _parse_time(row["start_time"])
                end = _parse_time(row["end_time"])
            except (KeyError, ValueError, TypeError):
                raise PosError("Tanggal/jam booking tidak valid", "bad_booking_time")
            hours = _hours_between(start, end)
            if hours <= 0:
                raise PosError("Jam selesai harus setelah jam mulai", "bad_booking_range")
            if not is_slot_available(facility.id, bdate, start, end):
                raise PosError(
                    f"Jadwal {facility.name} {row['start_time']}-{row['end_time']} sudah dibooking",
                    "slot_taken", 409,
                )
            for _, fid2, d2, s2, e2 in booking_specs:  # bentrok dalam 1 keranjang
                if fid2 == facility.id and d2 == bdate and s2 < end and e2 > start:
                    raise PosError("Slot bentrok dengan item lain di keranjang", "slot_taken", 409)
            qty = _D(hours)
            unit_price = _D(facility.hourly_rate)
            name = f"{facility.name} {bdate:%d/%m} {row['start_time']}-{row['end_time']}"
            oi = OrderItem(
                item_type="booking", product_id=None, name_snapshot=name[:120],
                unit_price=unit_price, quantity=qty,
                line_total=(unit_price * qty).quantize(Decimal("0.01")),
            )
            booking_specs.append((oi, facility.id, bdate, start, end))

        else:  # ticket | rental: nama & harga dari input
            qty = _D(row.get("quantity", 1))
            if qty <= 0:
                raise PosError("Quantity harus > 0", "bad_quantity")
            unit_price = _D(row.get("unit_price"))
            oi = OrderItem(
                item_type=item_type, product_id=row.get("product_id"),
                name_snapshot=(row.get("name") or item_type)[:120],
                unit_price=unit_price, quantity=qty,
                line_total=(unit_price * qty).quantize(Decimal("0.01")),
            )

        subtotal += oi.line_total
        order.items.append(oi)

    discount = _D(data.get("discount_amount"))
    if discount < 0 or discount > subtotal:
        raise PosError("Diskon tidak valid", "bad_discount")
    order.subtotal = subtotal
    order.discount_amount = discount
    order.total_amount = subtotal - discount

    db.session.add(order)
    db.session.flush()

    # buat facility_bookings setelah order_item punya id (reservasi slot)
    for oi, fid, bdate, start, end in booking_specs:
        db.session.add(
            FacilityBooking(
                facility_id=fid, venue_id=order.venue_id, order_item_id=oi.id,
                booking_date=bdate, start_time=start, end_time=end, status="booked",
            )
        )
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


def pay_order(order: Order, shift: Shift, cashier_id: int, data: dict) -> Payment:
    """Terima pembayaran (penuh, DP, atau pelunasan) pada order.

    `data.amount` opsional: jika kosong = bayar seluruh sisa. Jika < sisa = DP.
    Pembayaran dicatat pada `shift` yang menerimanya (bisa beda dari shift order).
    """
    if order.status not in ("open", "partial"):
        raise PosError("Order sudah tidak bisa dibayar", "order_not_open")

    remaining = _D(order.total_amount) - _D(order.amount_paid)
    if remaining <= 0:
        raise PosError("Order sudah lunas", "already_paid")

    method = data.get("method")
    if method not in VALID_METHODS:
        raise PosError("Metode bayar tidak valid (cash|qris)", "bad_method")
    provider = data.get("provider") or ("cash" if method == "cash" else "bri_qris_mpm")
    if provider not in PROVIDERS:
        raise PosError(f"Provider tidak dikenal: {provider}", "bad_provider")

    amt_in = data.get("amount")
    amount = remaining if amt_in in (None, "", 0, "0") else _D(amt_in)
    if amount <= 0 or amount > remaining:
        raise PosError(
            f"Jumlah bayar harus antara 1 dan {remaining} (sisa tagihan)", "bad_amount"
        )

    payment = Payment(
        order_id=order.id, method=method, provider=provider, amount=amount,
        status="pending", reference=(data.get("reference") or None),
        confirmed_by=cashier_id, shift_id=shift.id,
    )
    db.session.add(payment)

    PROVIDERS[provider](order, payment, data=data)

    if payment.status == "paid":
        _apply_payment(order, payment, shift, cashier_id)

    db.session.commit()
    return payment


def _apply_payment(order: Order, payment: Payment, shift: Shift, cashier_id: int) -> None:
    """Terapkan pembayaran lunas: akumulasi shift + update status order + stok."""
    amt = _D(payment.amount)

    # akuntansi pada shift yang MENERIMA pembayaran ini (DP & pelunasan terpisah)
    shift.total_sales = _D(shift.total_sales) + amt
    if payment.method == "cash":
        shift.total_cash_sales = _D(shift.total_cash_sales) + amt
    elif payment.method == "qris":
        shift.total_qris_sales = _D(shift.total_qris_sales) + amt

    was_paid = order.status == "paid"
    order.amount_paid = _D(order.amount_paid) + amt
    order.updated_at = datetime.utcnow()

    if order.amount_paid >= _D(order.total_amount):
        order.status = "paid"
        if not was_paid:
            _deduct_stock(order, cashier_id)
    else:
        order.status = "partial"


def cancel_order(order: Order) -> Order:
    """Batalkan booking (no-show): order → void, slot dilepas, DP hangus (tak di-refund)."""
    if order.status not in ("open", "partial"):
        raise PosError(
            "Hanya order belum lunas yang bisa dibatalkan", "cannot_cancel", 409
        )
    order.status = "void"
    order.updated_at = datetime.utcnow()
    # lepas slot lapangan yang terkait item order ini
    item_ids = [i.id for i in order.items]
    if item_ids:
        FacilityBooking.query.filter(
            FacilityBooking.order_item_id.in_(item_ids),
            FacilityBooking.status == "booked",
        ).update({FacilityBooking.status: "cancelled"}, synchronize_session=False)
    db.session.commit()
    return order


def _deduct_stock(order: Order, cashier_id: int) -> None:
    """Kurangi stok produk (sekali, saat order lunas penuh)."""
    for item in order.items:
        if item.item_type == "product" and item.product_id:
            product = db.session.get(Product, item.product_id)
            if product and product.track_stock:
                qty = int(item.quantity)
                product.stock_qty -= qty
                db.session.add(
                    StockMovement(
                        product_id=product.id, venue_id=order.venue_id, type="sale",
                        quantity=-qty, balance_after=product.stock_qty,
                        reference=order.order_number, created_by=cashier_id,
                    )
                )


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
