"""Logika bisnis POS: order, pembayaran (provider), shift, stok."""
import logging
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from ..extensions import db
from ..models import Venue
from . import briapi

log = logging.getLogger(__name__)
from .models import (
    CashMovement,
    Facility,
    FacilityBooking,
    Holiday,
    Order,
    OrderItem,
    Payment,
    Product,
    Shift,
    StockMovement,
    day_type_for_date,
    facility_booking_price,
)


def is_weekend(d) -> bool:
    """True bila tanggal = Sabtu/Minggu ATAU hari libur nasional (tabel holidays)."""
    if d.weekday() >= 5:  # 5=Sabtu, 6=Minggu
        return True
    return db.session.query(Holiday.id).filter_by(date=d).first() is not None


def ticket_unit_price(product, on_date=None) -> float:
    """Harga tiket berlaku: weekend_price bila weekend/libur & terisi, else price (weekday)."""
    on_date = on_date or date.today()
    if is_weekend(on_date) and product.weekend_price is not None:
        return float(product.weekend_price)
    return float(product.price or 0)


def _parse_time(s):
    return datetime.strptime(s, "%H:%M").time()


def _hours_between(start, end) -> float:
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    if e <= s:
        e += 24 * 60  # booking berakhir tengah malam (00:00) / lewat tengah malam
    return (e - s) / 60.0


def is_slot_available(facility_id, booking_date, start, end, exclude_id=None) -> bool:
    """True jika slot [start,end) di tanggal itu belum dibooking (tanpa overlap).
    Dihitung di Python (bukan filter SQL langsung) krn jam 00:00 = tengah malam
    (akhir hari) baik utk slot baru maupun booking lama — perbandingan TIME
    mentah di SQL salah baca 00:00 sbg 'paling awal', bukan 'paling akhir'."""
    def _mins(t, as_end=False):
        m = t.hour * 60 + t.minute
        return 24 * 60 if (as_end and m == 0) else m

    s_min = _mins(start)
    e_min = _mins(end, as_end=True)

    q = FacilityBooking.query.filter(
        FacilityBooking.facility_id == facility_id,
        FacilityBooking.booking_date == booking_date,
        FacilityBooking.status == "booked",
    )
    if exclude_id:
        q = q.filter(FacilityBooking.id != exclude_id)
    for b in q.all():
        if _mins(b.start_time) < e_min and _mins(b.end_time, as_end=True) > s_min:
            return False
    return True

VALID_ITEM_TYPES = {"product", "ticket", "rental", "booking"}
VALID_METHODS = {"cash", "qris", "transfer"}


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
    # ambil nomor urut TERBESAR yg sudah ada, BUKAN count — kalau ada order
    # yg dihapus permanen (Hapus Permanen di Riwayat Transaksi), count turun
    # tapi nomor yg lebih besar tetap ada, jadi count+1 bisa tabrakan dgn
    # nomor yg masih hidup (UniqueViolation, order gagal dibuat)
    existing = (
        db.session.query(Order.order_number)
        .filter(Order.order_number.like(prefix + "%"))
        .all()
    )
    max_seq = 0
    for (num,) in existing:
        try:
            max_seq = max(max_seq, int(num.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return f"{prefix}{max_seq + 1:04d}"


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
            from .promos import active_promo, compute_line, promo_label

            promo = active_promo(product.id)
            unit, line_total = compute_line(product, qty, promo)
            pname = f"{product.name} ({promo_label(promo)})" if promo else product.name
            oi = OrderItem(
                item_type="product", product_id=product.id, name_snapshot=pname[:120],
                unit_price=unit, quantity=qty, line_total=line_total,
            )

        elif item_type == "ticket":
            qty = _D(row.get("quantity", 1))
            if qty <= 0:
                raise PosError("Quantity harus > 0", "bad_quantity")
            product = db.session.get(Product, row.get("product_id"))
            if product is None or not product.is_active or not product.is_ticket:
                raise PosError("Tiket tidak ditemukan/nonaktif", "ticket_not_found", 404)
            if product.venue_id != shift.venue_id:
                raise PosError("Tiket bukan milik venue ini", "ticket_wrong_venue")
            unit = _D(ticket_unit_price(product))  # harga weekday/weekend otomatis
            oi = OrderItem(
                item_type="ticket", product_id=product.id, name_snapshot=product.name[:120],
                unit_price=unit, quantity=qty, line_total=unit * qty,
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
            # tarif bisa beda per rentang jam (facility.rate_rules, mis. malam
            # lebih mahal) — hitung per jam lalu jumlahkan, bukan flat hourly_rate*qty
            end_hour = start.hour + int(hours)
            dtype = day_type_for_date(bdate)  # weekday/saturday/sunday/holiday
            total_price = _D(facility_booking_price(facility, start.hour, end_hour, dtype)).quantize(Decimal("0.01"))
            unit_price = (total_price / qty).quantize(Decimal("0.01")) if qty else _D(0)
            name = f"{facility.name} {bdate:%d/%m} {row['start_time']}-{row['end_time']}"
            oi = OrderItem(
                item_type="booking", product_id=None, name_snapshot=name[:120],
                unit_price=unit_price, quantity=qty,
                line_total=total_price,
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
# Provider pembayaran (colok-lepas)
# ------------------------------------------------------------------
def _pay_cash(order, payment, **_):
    payment.status = "paid"
    payment.paid_at = datetime.utcnow()


def _to_naive_utc(dt):
    """Datetime ber-timezone → UTC polos, sesuai konvensi kolom waktu di DB."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def new_external_id(payment_id: int) -> str:
    """partnerReferenceNo unik & tak bisa ditebak.

    Dipakai juga sebagai kunci pencocokan notifikasi BRI, jadi ada komponen acak
    supaya orang luar tak bisa menebak nomor referensi transaksi lain.
    """
    return f"ASP{payment_id:08d}{secrets.token_hex(6).upper()}"  # 8+3+12 = 23 char


def _pay_qris_bri(order, payment, **_):
    """QRIS MPM Dinamis: minta QR bernominal terkunci ke BRI.

    Pembayaran tetap 'pending' sampai BRI mengonfirmasi lewat webhook (atau
    hasil polling `sync_qris_payment`) — uang tak pernah diakui dari sisi kasir.
    """
    if not briapi.is_configured():
        # Integrasi dinamis belum nyala → mode MANUAL, diperlakukan seperti
        # transfer bank: bukti pembayaran QRIS wajib diupload (dicek di pay_order)
        # dan kasir sudah memverifikasi dana masuk sebelum konfirmasi. Langsung
        # lunas; metode tetap tercatat 'qris' supaya rekonsiliasi bank benar.
        payment.status = "paid"
        payment.paid_at = datetime.utcnow()
        return

    db.session.flush()  # butuh payment.id utk menyusun external_id
    ext = new_external_id(payment.id)
    try:
        res = briapi.generate_qr(ext, payment.amount)
    except briapi.BriError as e:
        # Jangan tinggalkan pembayaran menggantung tanpa QR — batalkan supaya
        # kasir langsung tahu dan bisa pilih metode lain (cash/transfer).
        db.session.rollback()
        log.warning("QRIS generate gagal (order %s): %s", order.id, e)
        raise PosError(
            "QRIS sedang tidak bisa dipakai. Coba lagi atau pakai metode lain.",
            "qris_unavailable", 502,
        )

    payment.external_id = ext
    payment.qr_content = res["qr_content"]
    payment.bri_reference_no = res["bri_reference_no"]
    payment.qr_expires_at = _to_naive_utc(res["expires_at"])
    payment.status = "pending"


def _pay_transfer(order, payment, **_):
    # Transfer bank manual — kasir sudah cek bukti transfer sebelum konfirmasi
    # (wajib upload, lihat pay_order), jadi langsung dianggap lunas spt cash.
    payment.status = "paid"
    payment.paid_at = datetime.utcnow()


PROVIDERS = {
    "cash": _pay_cash,
    "bri_qris_mpm": _pay_qris_bri,
    "bank_transfer": _pay_transfer,
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
        raise PosError("Metode bayar tidak valid (cash|qris|transfer)", "bad_method")
    if method == "transfer" and not data.get("proof_filename"):
        raise PosError("Bukti transfer wajib diupload", "proof_required")
    # QRIS mode manual (BRIAPI belum aktif) diperlakukan spt transfer: wajib bukti.
    if method == "qris" and not briapi.is_configured() and not data.get("proof_filename"):
        raise PosError("Bukti pembayaran QRIS wajib diupload", "proof_required")
    _default_provider = {"cash": "cash", "transfer": "bank_transfer"}
    provider = data.get("provider") or _default_provider.get(method, "bri_qris_mpm")
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
        proof_image=data.get("proof_filename"),
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
    elif payment.method == "transfer":
        shift.total_transfer_sales = _D(shift.total_transfer_sales) + amt

    was_paid = order.status == "paid"
    order.amount_paid = _D(order.amount_paid) + amt
    order.updated_at = datetime.utcnow()

    if order.amount_paid >= _D(order.total_amount):
        order.status = "paid"
        if not was_paid:
            _deduct_stock(order, cashier_id)
    else:
        order.status = "partial"


# ------------------------------------------------------------------
# Konfirmasi QRIS (dipanggil dari webhook BRI maupun polling status)
# ------------------------------------------------------------------
def confirm_qris_payment(payment: Payment, bri_reference_no: str = None) -> bool:
    """Tandai pembayaran QRIS lunas & terapkan ke order + shift. Idempoten.

    Mengembalikan True hanya kalau panggilan INI yang mengubah status pending →
    paid. Panggilan berikutnya (webhook dikirim ulang, polling balapan dgn
    webhook) mengembalikan False dan tidak menambah uang lagi.

    Pemanggil WAJIB sudah mengunci baris payment (SELECT ... FOR UPDATE) supaya
    dua proses tidak sama-sama lolos pengecekan status di bawah.
    """
    if payment.status == "paid":
        return False  # sudah pernah dikonfirmasi — jangan kredit dua kali
    if payment.status == "void":
        log.warning("Notifikasi lunas utk payment void #%s — diabaikan", payment.id)
        return False

    order = db.session.get(Order, payment.order_id)
    if order is None:
        log.error("Payment #%s menunjuk order hilang", payment.id)
        return False

    shift = db.session.get(Shift, payment.shift_id) if payment.shift_id else None
    if shift is None:
        log.error("Payment #%s tanpa shift — tak bisa dibukukan", payment.id)
        return False
    if shift.status == "closed":
        # Uang QRIS masuk ke rekening bank (bukan laci kas), jadi setoran tunai
        # shift tidak terpengaruh. Tetap dibukukan ke shift yg melakukan
        # penjualan supaya laporan penjualan konsisten dgn tanggal ordernya.
        log.warning(
            "Pembayaran QRIS #%s dikonfirmasi setelah shift #%s ditutup — "
            "total QRIS shift itu ikut disesuaikan", payment.id, shift.id
        )

    payment.status = "paid"
    payment.paid_at = datetime.utcnow()
    payment.paid_notified_at = datetime.utcnow()
    if bri_reference_no:
        payment.bri_reference_no = bri_reference_no

    _apply_payment(order, payment, shift, payment.confirmed_by)
    return True


def sync_qris_payment(payment: Payment) -> str:
    """Tanya status ke BRI lalu selaraskan status lokal. Kembalikan status akhir.

    Dipakai sebagai cadangan kalau webhook telat/tidak sampai, dan saat kasir
    menekan "Cek status" di layar QR.
    """
    if payment.status != "pending" or not payment.external_id:
        return payment.status
    if not briapi.is_configured():
        return payment.status

    try:
        res = briapi.query_qr(payment.external_id, payment.bri_reference_no)
    except briapi.BriError as e:
        log.warning("Query status QRIS payment #%s gagal: %s", payment.id, e)
        return payment.status  # jangan ubah apa pun kalau BRI tak bisa dihubungi

    if res["status"] == "paid":
        confirm_qris_payment(payment, res.get("bri_reference_no"))
    elif res["status"] == "failed":
        payment.status = "failed"
    return payment.status


def expire_stale_qris(payment: Payment) -> None:
    """Tandai 'failed' kalau QR sudah lewat masa berlaku & belum dibayar."""
    if (
        payment.status == "pending"
        and payment.qr_expires_at
        and payment.qr_expires_at < datetime.utcnow()
    ):
        payment.status = "failed"


def cancel_order(order: Order, uid: int = None) -> Order:
    """Batalkan transaksi → order jadi 'void', slot lapangan dilepas.
    - open/partial: DP yg sudah masuk hangus (tak direfund), tak ada stok/shift
      yg perlu dibalik (belum ada yg lunas penuh).
    - paid: BALIKKAN efeknya — stok yg sudah terjual dikembalikan (dicatat sbg
      penyesuaian, bukan dihapus dr riwayat) & akumulasi shift dikurangi lagi.
      Payment yg sudah 'paid' ditandai 'void' (keluar dari perhitungan laporan
      manapun, tapi barisnya tetap ada utk audit). DITOLAK kalau shift penerima
      pembayarannya sudah ditutup (sudah masuk rekonsiliasi kas / disetor —
      tak aman diubah retroaktif)."""
    if order.status not in ("open", "partial", "paid"):
        raise PosError("Order sudah dibatalkan/tidak valid", "cannot_cancel", 409)

    if order.status == "paid":
        paid_payments = [p for p in order.payments if p.status == "paid"]
        shift_ids = {p.shift_id for p in paid_payments if p.shift_id}
        if shift_ids:
            closed = Shift.query.filter(Shift.id.in_(shift_ids), Shift.status == "closed").count()
            if closed:
                raise PosError(
                    "Shift penerima pembayaran order ini sudah ditutup — tidak bisa "
                    "dibatalkan otomatis (sudah masuk rekonsiliasi kas).",
                    "shift_closed", 409,
                )
        # balikkan stok yg sudah dikurangi saat lunas
        for item in order.items:
            if item.item_type == "product" and item.product_id:
                product = db.session.get(Product, item.product_id)
                if product and product.track_stock:
                    qty = int(item.quantity)
                    product.stock_qty += qty
                    db.session.add(StockMovement(
                        product_id=product.id, venue_id=order.venue_id, type="adjustment",
                        quantity=qty, balance_after=product.stock_qty,
                        reference=order.order_number, created_by=uid,
                    ))
        # balikkan akumulasi shift & tandai payment void (tanpa hapus baris)
        for p in paid_payments:
            if p.shift_id:
                shift = db.session.get(Shift, p.shift_id)
                if shift:
                    amt = Decimal(str(p.amount))
                    shift.total_sales = Decimal(str(shift.total_sales or 0)) - amt
                    if p.method == "cash":
                        shift.total_cash_sales = Decimal(str(shift.total_cash_sales or 0)) - amt
                    elif p.method == "qris":
                        shift.total_qris_sales = Decimal(str(shift.total_qris_sales or 0)) - amt
                    elif p.method == "transfer":
                        shift.total_transfer_sales = Decimal(str(shift.total_transfer_sales or 0)) - amt
            p.status = "void"

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
