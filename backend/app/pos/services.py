"""Logika bisnis POS: order, pembayaran (provider), shift, stok."""
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from ..extensions import db
from ..models import Venue
from . import briapi

log = logging.getLogger(__name__)
from .models import (
    BookingReschedule,
    CashMovement,
    Coach,
    CoachingRate,
    Event,
    Facility,
    FacilityBooking,
    Holiday,
    Order,
    OrderItem,
    Payment,
    Product,
    Shift,
    StockMovement,
    coach_declared_available,
    coaching_price_per_hour,
    day_type_for_date,
    facility_booking_price,
    facility_rate_for_hour,
)


def _booking_rate_breakdown(facility, start_hour, end_hour, day_type):
    """Rincian tarif per jam sbg teks utk struk, mengelompokkan jam berturut yg
    tarifnya sama. Return None kalau seluruh jam tarifnya seragam (tak perlu
    rincian). Contoh: '15:00–16:00: Rp 200.000/jam · 16:00–17:00: Rp 250.000/jam'."""
    segs = []  # (mulai, selesai, tarif)
    for h in range(start_hour, end_hour):
        rate = facility_rate_for_hour(facility, h, day_type)
        if segs and segs[-1][2] == rate:
            segs[-1] = (segs[-1][0], h + 1, rate)
        else:
            segs.append((h, h + 1, rate))
    if len(segs) <= 1:
        return None  # tarif seragam → tak perlu rincian
    hhmm = lambda x: f"{x % 24:02d}:00"
    rp = lambda n: "Rp " + f"{int(n):,}".replace(",", ".")
    return " · ".join(f"{hhmm(a)}–{hhmm(b)}: {rp(r)}/jam" for a, b, r in segs)


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


def _t_mins(t, as_end=False):
    m = t.hour * 60 + t.minute
    return 24 * 60 if (as_end and m == 0) else m


def active_event_ranges(venue_id, booking_date):
    """Rentang jam yang DIKUNCI oleh event aktif (borong semua lapangan) pada
    venue+tanggal itu. Return list dict {start, end, name} (HH:MM)."""
    evs = Event.query.filter(
        Event.venue_id == venue_id,
        Event.status == "active",
        Event.date_from <= booking_date,
        Event.date_to >= booking_date,
    ).all()
    return [
        {"start": e.start_time.strftime("%H:%M"), "end": e.end_time.strftime("%H:%M"), "name": e.name}
        for e in evs
    ]


def event_price_quote(venue_id, date_from, date_to, start_t, end_t):
    """Harga usulan event = tarif normal semua lapangan aktif × jam × jumlah hari."""
    facs = Facility.query.filter_by(venue_id=venue_id, is_active=True).all()
    sh = start_t.hour
    eh = end_t.hour if end_t.hour != 0 else 24
    total = 0.0
    d = date_from
    while d <= date_to:
        dt = day_type_for_date(d)
        for f in facs:
            total += float(facility_booking_price(f, sh, eh, dt))
        d += timedelta(days=1)
    return round(total, 2), len(facs)


def event_conflicts(venue_id, date_from, date_to, start_t, end_t, exclude_order_id=None):
    """Booking (member/reguler) yang bentrok dgn jam event pada rentang tanggal."""
    fac_ids = [f.id for f in Facility.query.filter_by(venue_id=venue_id).all()]
    if not fac_ids:
        return []
    e_min, s_min = _t_mins(end_t, as_end=True), _t_mins(start_t)
    rows = FacilityBooking.query.filter(
        FacilityBooking.facility_id.in_(fac_ids),
        FacilityBooking.booking_date >= date_from,
        FacilityBooking.booking_date <= date_to,
        FacilityBooking.status == "booked",
    ).all()
    fac_names = {f.id: f.name for f in Facility.query.filter(Facility.id.in_(fac_ids)).all()}
    out = []
    for b in rows:
        if not (_t_mins(b.start_time) < e_min and _t_mins(b.end_time, as_end=True) > s_min):
            continue
        oi = db.session.get(OrderItem, b.order_item_id) if b.order_item_id else None
        order = oi.order if oi else None
        if order is None or order.status == "void":
            continue
        if exclude_order_id and order.id == exclude_order_id:
            continue
        out.append({
            "booking_id": b.id,
            "order_id": order.id,
            "order_item_id": b.order_item_id,
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "is_member": order.is_member,
            "status": order.status,
            "facility_name": fac_names.get(b.facility_id),
            "booking_date": b.booking_date.isoformat(),
            "start_time": b.start_time.strftime("%H:%M"),
            "end_time": b.end_time.strftime("%H:%M"),
        })
    out.sort(key=lambda x: (x["booking_date"], x["start_time"]))
    return out


def event_blocks_slot(venue_id, booking_date, start, end):
    """True bila slot [start,end) bentrok dgn event aktif di venue+tanggal itu."""
    s_min = _t_mins(start)
    e_min = _t_mins(end, as_end=True)
    evs = Event.query.filter(
        Event.venue_id == venue_id,
        Event.status == "active",
        Event.date_from <= booking_date,
        Event.date_to >= booking_date,
    ).all()
    for e in evs:
        if _t_mins(e.start_time) < e_min and _t_mins(e.end_time, as_end=True) > s_min:
            return True
    return False


def is_slot_available(facility_id, booking_date, start, end, exclude_id=None) -> bool:
    """True jika slot [start,end) di tanggal itu belum dibooking (tanpa overlap).
    Dihitung di Python (bukan filter SQL langsung) krn jam 00:00 = tengah malam
    (akhir hari) baik utk slot baru maupun booking lama — perbandingan TIME
    mentah di SQL salah baca 00:00 sbg 'paling awal', bukan 'paling akhir'.
    Slot juga TAK tersedia bila terkunci event (borong semua lapangan)."""
    _mins = _t_mins
    s_min = _mins(start)
    e_min = _mins(end, as_end=True)

    # terkunci event? (event mengunci semua lapangan venue)
    fac = db.session.get(Facility, facility_id)
    if fac and event_blocks_slot(fac.venue_id, booking_date, start, end):
        return False

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

def is_coach_available(coach_id, booking_date, start, end, exclude_id=None) -> bool:
    """True jika coach belum mengajar di slot [start,end) pd tanggal itu.
    Dicek LINTAS COURT (bukan per facility spt is_slot_available): 1 coach tak
    bisa mengajar di 2 court sekaligus, walau court-nya sendiri kosong."""
    def _mins(t, as_end=False):
        m = t.hour * 60 + t.minute
        return 24 * 60 if (as_end and m == 0) else m

    s_min = _mins(start)
    e_min = _mins(end, as_end=True)

    q = FacilityBooking.query.filter(
        FacilityBooking.coach_id == coach_id,
        FacilityBooking.booking_date == booking_date,
        FacilityBooking.status == "booked",
    )
    if exclude_id:
        q = q.filter(FacilityBooking.id != exclude_id)
    for b in q.all():
        if _mins(b.start_time) < e_min and _mins(b.end_time, as_end=True) > s_min:
            return False
    return True


def coach_conflicting_sessions(coach_id):
    """Sesi MENDATANG yg kini jatuh di luar ketersediaan coach — dipakai utk
    memperingatkan (halaman coach) & menandai (portal manajer). Sengaja hanya
    laporan: booking berbayar TAK PERNAH dibatalkan otomatis gara-gara coach
    mengubah ketersediaannya.

    Dipakai bersama blueprint public & admin — jangan disalin ulang; dua
    salinan pasti menyimpang (spt kasus bookingPrice.js dulu)."""
    today = date.today()
    rows = (
        db.session.query(FacilityBooking, Facility)
        .join(Facility, FacilityBooking.facility_id == Facility.id)
        .filter(
            FacilityBooking.coach_id == coach_id,
            FacilityBooking.status == "booked",
            FacilityBooking.booking_date >= today,
        )
        .order_by(FacilityBooking.booking_date, FacilityBooking.start_time)
        .all()
    )
    out = []
    for fb, fac in rows:
        if coach_declared_available(coach_id, fb.booking_date, fb.start_time, fb.end_time):
            continue
        out.append({
            "booking_id": fb.id,
            "date": fb.booking_date.isoformat(),
            "start_time": fb.start_time.strftime("%H:%M"),
            "end_time": fb.end_time.strftime("%H:%M"),
            "facility_name": fac.name,
            "override": bool(fb.coaching_override),
        })
    return out


# 'coaching' tak boleh dikirim langsung dr klien — baris uangnya dibuat otomatis
# oleh sistem dari item 'booking' yg memakai coach (lihat _build_order_items).
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


def _build_order_items(order, items_in, venue_id):
    """Bangun OrderItem dari `items_in`, append ke `order.items`, return
    (subtotal_item, booking_specs). TIDAK mengubah subtotal/total order & tidak
    membuat FacilityBooking (butuh order_item.id → urusan pemanggil). Dipakai
    bersama create_order (bill baru) & add_items_to_order (tambah ke open bill)."""
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
            if product.venue_id != venue_id:
                raise PosError("Produk bukan milik venue ini", "product_wrong_venue")
            if product.open_price:
                # harga terbuka (mis. Parkir): nominal diketik kasir, tak ada
                # stok/promo. Ambil dari input, wajib > 0.
                unit = _D(row.get("unit_price"))
                if unit <= 0:
                    raise PosError(f"Nominal '{product.name}' harus diisi (> 0)", "bad_amount")
                oi = OrderItem(
                    item_type="product", product_id=product.id, name_snapshot=product.name[:120],
                    unit_price=unit, quantity=qty,
                    line_total=(unit * qty).quantize(Decimal("0.01")),
                )
            else:
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
            if product.venue_id != venue_id:
                raise PosError("Tiket bukan milik venue ini", "ticket_wrong_venue")
            unit = _D(ticket_unit_price(product))  # harga weekday/weekend otomatis
            oi = OrderItem(
                item_type="ticket", product_id=product.id, name_snapshot=product.name[:120],
                unit_price=unit, quantity=qty, line_total=unit * qty,
            )

        elif item_type == "booking":
            facility = db.session.get(Facility, row.get("facility_id"))
            if facility is None or not facility.is_active or facility.venue_id != venue_id:
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
            for spec in booking_specs:  # bentrok dalam 1 keranjang
                _, fid2, d2, s2, e2 = spec[:5]
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
            # rincian tarif per jam kalau tak seragam (mis. 15-16 @200rb, 16-17
            # @250rb) — supaya struk menampilkan pecahan sebenarnya, bukan rata2.
            breakdown = _booking_rate_breakdown(facility, start.hour, end_hour, dtype)
            oi = OrderItem(
                item_type="booking", product_id=None, name_snapshot=name[:120],
                unit_price=unit_price, quantity=qty,
                line_total=total_price, notes=breakdown,
            )

            # --- coaching (padel): opsional, selalu menempel pd booking ini ---
            coach_id = row.get("coach_id")
            coaching_oi = None
            coach_override = False
            if coach_id:
                coach = db.session.get(Coach, coach_id)
                if coach is None or not coach.is_active or coach.venue_id != venue_id:
                    raise PosError("Coach tidak ditemukan/nonaktif", "coach_not_found", 404)
                rate = db.session.get(CoachingRate, venue_id)
                if rate is None:
                    raise PosError(
                        "Tarif coaching belum diatur utk venue ini", "no_coaching_rate", 409
                    )
                persons = int(row.get("coaching_persons") or 1)
                if persons < 1 or persons > (rate.max_persons or 4):
                    raise PosError(
                        f"Jumlah peserta coaching harus 1–{rate.max_persons or 4}", "bad_persons"
                    )
                if not is_coach_available(coach.id, bdate, start, end):
                    raise PosError(
                        f"{coach.name} sudah mengajar di jam {row['start_time']}-{row['end_time']}",
                        "coach_taken", 409,
                    )
                # di luar jam ketersediaan yg coach nyatakan → boleh, TAPI kasir
                # harus konfirmasi dulu (coach_override). Jejaknya disimpan di
                # slot booking utk kalau nanti ada sengketa dgn coach.
                coach_override = bool(row.get("coach_override"))
                if not coach_declared_available(coach.id, bdate, start, end):
                    if not coach_override:
                        raise PosError(
                            f"{coach.name} tidak menyatakan diri tersedia pada "
                            f"{bdate:%d/%m} {row['start_time']}-{row['end_time']}. "
                            "Pastikan coach sudah setuju, lalu centang konfirmasi.",
                            "coach_unavailable", 409,
                        )
                else:
                    coach_override = False  # tak perlu ditandai kalau memang tersedia
                for spec in booking_specs:  # coach bentrok dalam 1 keranjang
                    _, _, d2, s2, e2 = spec[:5]
                    if spec[5] == coach.id and d2 == bdate and s2 < end and e2 > start:
                        raise PosError(
                            f"{coach.name} bentrok dengan item lain di keranjang",
                            "coach_taken", 409,
                        )
                per_hour = _D(coaching_price_per_hour(rate, persons))
                c_total = (per_hour * qty).quantize(Decimal("0.01"))
                c_name = f"Coaching {persons} orang — {facility.name} {bdate:%d/%m} {row['start_time']}-{row['end_time']}"
                extra = persons - 1
                c_note = f"{per_hour:,.0f}/jam × {hours:g} jam".replace(",", ".")
                if extra:
                    c_note = (
                        f"{float(rate.base_price):,.0f} + {extra}×{float(rate.extra_person_price):,.0f} "
                        f"= {c_note}"
                    ).replace(",", ".")
                coaching_oi = OrderItem(
                    item_type="coaching", product_id=None, name_snapshot=c_name[:120],
                    unit_price=per_hour, quantity=qty, line_total=c_total, notes=c_note,
                )

            booking_specs.append(
                (oi, facility.id, bdate, start, end, coach_id, coaching_oi,
                 int(row.get("coaching_persons") or 1) if coach_id else None,
                 coach_override)
            )

        else:  # rental: nama & harga dari input
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
        # baris uang coaching (kalau booking ini pakai coach) — item terpisah
        # supaya terpisah juga di laporan
        c_oi = booking_specs[-1][6] if (item_type == "booking" and booking_specs) else None
        if c_oi is not None:
            subtotal += c_oi.line_total
            order.items.append(c_oi)
    return subtotal, booking_specs


def _create_facility_bookings(order, booking_specs):
    """Reservasi slot (FacilityBooking) utk item booking — setelah order_item punya id."""
    for spec in booking_specs:
        oi, fid, bdate, start, end = spec[:5]
        coach_id, c_oi, persons, override = spec[5], spec[6], spec[7], spec[8]
        db.session.add(
            FacilityBooking(
                facility_id=fid, venue_id=order.venue_id, order_item_id=oi.id,
                booking_date=bdate, start_time=start, end_time=end, status="booked",
                coach_id=coach_id, coaching_persons=persons,
                coaching_item_id=c_oi.id if c_oi is not None else None,
                coaching_override=bool(override),
            )
        )


def add_items_to_order(order: Order, items_in: list) -> Order:
    """Tambah item ke bill (order) yang masih TERBUKA — inti open bill. Stok baru
    dipotong saat bill dibayar lunas (lihat _apply_payment), jadi di sini hanya
    menambah item & menghitung ulang total (diskon awal dipertahankan)."""
    if not items_in:
        raise PosError("Tak ada item untuk ditambahkan", "empty_order")
    # open bill (open/partial) ATAU running-tab station yang durasinya sudah dibayar
    # (paid) tapi F&B/topup menyusul. Void tak boleh.
    if order.status == "void":
        raise PosError("Bill sudah dibatalkan", "bill_not_open", 409)
    add_subtotal, booking_specs = _build_order_items(order, items_in, order.venue_id)
    db.session.flush()  # item baru dapat id utk reservasi slot
    _create_facility_bookings(order, booking_specs)
    order.subtotal = _D(order.subtotal) + add_subtotal
    order.total_amount = _D(order.subtotal) - _D(order.discount_amount)
    # kalau menambah ke order yang tadinya lunas → jadi 'partial' lagi (masih ada sisa)
    paid = _D(order.amount_paid)
    if paid <= 0:
        order.status = "open"
    elif paid >= _D(order.total_amount):
        order.status = "paid"
    else:
        order.status = "partial"
    order.updated_at = datetime.utcnow()
    db.session.commit()
    return order


# ------------------------------------------------------------------
# Buat order (status open) + item; hitung total. Stok belum dikurangi.
# ------------------------------------------------------------------
def create_order(shift: Shift, cashier_id: int, data: dict) -> Order:
    items_in = data.get("items") or []
    if not items_in:
        raise PosError("Order tidak boleh kosong", "empty_order")

    # No HP WAJIB kalau ada item booking (agar data customer/CRM terisi & bisa dihubungi)
    if any(r.get("item_type") == "booking" for r in items_in) and not (data.get("customer_phone") or "").strip():
        raise PosError("No HP customer wajib diisi untuk booking", "phone_required")

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

    subtotal, booking_specs = _build_order_items(order, items_in, shift.venue_id)

    discount = _D(data.get("discount_amount"))
    if discount < 0 or discount > subtotal:
        raise PosError("Diskon tidak valid", "bad_discount")
    order.subtotal = subtotal
    order.discount_amount = discount
    order.total_amount = subtotal - discount

    db.session.add(order)
    db.session.flush()
    _create_facility_bookings(order, booking_specs)
    db.session.flush()
    return order


def reschedule_booking(order, item_id, facility_id, booking_date, start_time, end_time,
                       uid=None, refund_shift_id=None, record_refund=False,
                       coach_id=None, coach_override=False):
    """Pindah jadwal 1 slot booking ke slot baru (boleh beda court, dalam venue
    yg sama). DP TIDAK hangus — tetap tercatat; harga dihitung ulang sesuai tarif
    slot baru (sadar hari/jam) & total order diperbarui. Return (order, info)
    dgn selisih harga. Jejak lama→baru dicatat di log.

    `record_refund` (dipakai flow admin/manajer): kalau slot baru lebih murah dr
    yg SUDAH dibayar, kelebihannya dicatat otomatis sbg kas keluar di shift
    `refund_shift_id` (harus shift terbuka di venue ini) & amount_paid dikurangi
    supaya order pas lunas. Kalau tak ada shift terbuka → PosError (gagal bersih,
    tanpa mengubah slot). POS (default) tak memakai ini — perilakunya tetap.

    `coach_id` (opsional): GANTI coach pd booking ini — dipakai kalau coach lama
    ternyata tak bisa. None = pertahankan coach lama. Coach baru/lama tetap
    diperiksa: bentrok = ditolak keras; di luar jam ketersediaan = perlu
    `coach_override` (aturan sama persis dgn POS, supaya jalur reschedule tak
    jadi lubang)."""
    booking_items = [i for i in order.items if i.item_type == "booking"]
    if not booking_items:
        raise PosError("Order ini bukan booking", "not_booking", 400)
    if item_id:
        item = next((i for i in booking_items if i.id == item_id), None)
        if item is None:
            raise PosError("Item booking tidak ditemukan di order ini", "item_not_found", 404)
    elif len(booking_items) == 1:
        item = booking_items[0]
    else:
        raise PosError("Order punya beberapa booking — sebutkan item yang direschedule", "ambiguous_item", 400)

    fb = FacilityBooking.query.filter_by(order_item_id=item.id, status="booked").first()
    if fb is None:
        raise PosError("Slot booking tidak ditemukan/aktif", "slot_not_found", 404)

    facility = db.session.get(Facility, facility_id)
    if facility is None or not facility.is_active or facility.venue_id != order.venue_id:
        raise PosError("Lapangan tujuan tidak valid (harus di venue yang sama)", "bad_facility", 400)
    try:
        bdate = date.fromisoformat(booking_date)
        start = _parse_time(start_time)
        end = _parse_time(end_time)
    except (ValueError, TypeError):
        raise PosError("Tanggal/jam baru tidak valid", "bad_time", 400)
    hours = _hours_between(start, end)
    if hours <= 0:
        raise PosError("Jam selesai harus setelah jam mulai", "bad_range", 400)
    # slot baru harus kosong (kecuali slot ini sendiri)
    if not is_slot_available(facility.id, bdate, start, end, exclude_id=fb.id):
        raise PosError(f"Slot {facility.name} {start_time}-{end_time} sudah dibooking", "slot_taken", 409)
    # --- coaching: boleh sekalian GANTI COACH di sini (solusi paling wajar
    # kalau coach lama ternyata tak bisa). coach_id None = pertahankan yg lama.
    # Menghapus coaching sama sekali tak didukung lewat jalur ini — batalkan
    # ordernya kalau memang mau dibatalkan.
    new_coach_id = fb.coach_id
    if coach_id is not None and fb.coach_id:
        cand = db.session.get(Coach, coach_id)
        if cand is None or not cand.is_active or cand.venue_id != order.venue_id:
            raise PosError("Coach tujuan tidak valid", "coach_not_found", 404)
        new_coach_id = cand.id
    if new_coach_id:
        coach_obj = db.session.get(Coach, new_coach_id)
        nama = coach_obj.name if coach_obj else "Coach"
        # bentrok (sudah mengajar) = blokir keras, sama spt di POS
        if not is_coach_available(new_coach_id, bdate, start, end, exclude_id=fb.id):
            raise PosError(
                f"{nama} sudah mengajar di jam {start_time}-{end_time}", "coach_taken", 409,
            )
        # di luar jam ketersediaan = boleh, tapi harus dikonfirmasi — aturan yg
        # sama dgn POS supaya tak ada lubang lewat jalur reschedule
        if not coach_declared_available(new_coach_id, bdate, start, end):
            if not coach_override:
                raise PosError(
                    f"{nama} tidak menyatakan diri tersedia pada {bdate:%d/%m} "
                    f"{start_time}-{end_time}. Pastikan coach sudah setuju, lalu "
                    "centang konfirmasi.",
                    "coach_unavailable", 409,
                )
            fb.coaching_override = True
        else:
            fb.coaching_override = False
        fb.coach_id = new_coach_id

    old_desc = f"{item.name_snapshot}"
    old_line = _D(item.line_total)

    # harga baru
    end_hour = start.hour + int(hours)
    dtype = day_type_for_date(bdate)
    new_total = _D(facility_booking_price(facility, start.hour, end_hour, dtype)).quantize(Decimal("0.01"))
    breakdown = _booking_rate_breakdown(facility, start.hour, end_hour, dtype)

    # biaya coaching ikut durasi baru (tarif/jam & jumlah peserta tak berubah)
    c_item = db.session.get(OrderItem, fb.coaching_item_id) if fb.coaching_item_id else None
    c_old_line = _D(c_item.line_total) if c_item is not None else _D(0)
    c_new_line = c_old_line
    if c_item is not None:
        c_new_line = (_D(c_item.unit_price) * _D(hours)).quantize(Decimal("0.01"))

    # Pre-cek refund SEBELUM mengubah slot/harga (biar gagal tanpa efek samping):
    # kalau slot baru lebih murah dari yg sudah dibayar & diminta catat refund,
    # wajib ada shift kasir terbuka di venue utk mencatat kas keluar.
    new_order_total = (
        _D(order.subtotal) - old_line + new_total
        - c_old_line + c_new_line - _D(order.discount_amount)
    ).quantize(Decimal("0.01"))
    refund = _D(0)
    refund_shift = None
    if record_refund and _D(order.amount_paid) > new_order_total:
        refund = (_D(order.amount_paid) - new_order_total).quantize(Decimal("0.01"))
        refund_shift = db.session.get(Shift, refund_shift_id) if refund_shift_id else None
        if refund_shift is None or refund_shift.status != "open" or refund_shift.venue_id != order.venue_id:
            raise PosError(
                "Reschedule ini menimbulkan kelebihan bayar yang harus direfund tunai, "
                "tapi tak ada shift kasir terbuka di venue ini untuk mencatat kas keluar. "
                "Minta kasir buka shift dulu.", "no_open_shift", 409)

    # update item
    item.name_snapshot = f"{facility.name} {bdate:%d/%m} {start_time}-{end_time}"[:120]
    item.quantity = _D(hours)
    item.unit_price = (new_total / _D(hours)).quantize(Decimal("0.01")) if hours else _D(0)
    item.line_total = new_total
    item.notes = breakdown
    # update slot (slot lama otomatis lepas krn baris yg sama pindah)
    fb.facility_id = facility.id
    fb.booking_date = bdate
    fb.start_time = start
    fb.end_time = end
    # ikutkan baris coaching-nya (nama & durasi mengikuti slot baru)
    if c_item is not None:
        persons = fb.coaching_persons or 1
        c_item.name_snapshot = (
            f"Coaching {persons} orang — {facility.name} {bdate:%d/%m} {start_time}-{end_time}"
        )[:120]
        c_item.quantity = _D(hours)
        c_item.line_total = c_new_line

    # hitung ulang total order; DP (amount_paid) dipertahankan
    order.subtotal = _D(order.subtotal) - old_line + new_total - c_old_line + c_new_line
    order.total_amount = _D(order.subtotal) - _D(order.discount_amount)
    # refund kelebihan → kas keluar di shift terbuka (sudah divalidasi di pre-cek)
    if refund > 0:
        db.session.add(CashMovement(
            shift_id=refund_shift.id, type="out", amount=refund, created_by=uid,
            reason=f"Refund reschedule {order.order_number}: {old_desc} → {item.name_snapshot}"[:200],
        ))
        refund_shift.cash_out = _D(refund_shift.cash_out) + refund
        order.amount_paid = _D(order.total_amount)  # kelebihan sudah dikembalikan
    paid = _D(order.amount_paid)
    if paid > 0 and paid >= _D(order.total_amount):
        order.status = "paid"
    elif paid > 0:
        order.status = "partial"
    else:
        order.status = "open"
    order.updated_at = datetime.utcnow()

    diff = (_D(order.total_amount) - paid).quantize(Decimal("0.01"))  # >0 = kurang bayar, <0 = kelebihan
    db.session.add(BookingReschedule(
        order_id=order.id, order_item_id=item.id, from_desc=old_desc,
        to_desc=item.name_snapshot, from_price=old_line, to_price=new_total, created_by=uid,
    ))
    log.info("Reschedule order %s item %s: '%s' → '%s' (total %s→%s, sisa %s)",
             order.order_number, item.id, old_desc, item.name_snapshot, old_line, new_total, diff)
    db.session.commit()
    return order, {
        "old_line_total": float(old_line),
        "new_line_total": float(new_total),
        "amount_due": float(diff),  # >0 tagih ke customer; <0 kembalikan
        "refunded": float(refund),  # kelebihan yg dicatat sbg kas keluar (flow admin)
        "total_amount": float(order.total_amount),
        "amount_paid": float(paid),
    }


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


def pay_order(order: Order, shift: Shift, cashier_id: int, data: dict, commit: bool = True) -> Payment:
    """Terima pembayaran (penuh, DP, atau pelunasan) pada order.

    `data.amount` opsional: jika kosong = bayar seluruh sisa. Jika < sisa = DP.
    Pembayaran dicatat pada `shift` yang menerimanya (bisa beda dari shift order).
    `commit=False` dipakai split bill: beberapa pembayaran dalam 1 transaksi.
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

    if commit:
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


def edit_order_items_core(order, new_items):
    """Ganti item PRODUK/TIKET sebuah order (nama/qty/harga) + rekonsiliasi:
    total order, pembayaran (paid terakhir disesuaikan), & akumulasi shift.
    Item booking/rental TAK diubah (pakai reschedule/cancel). Tanggal & stok
    TIDAK diutak-atik. Return None kalau sukses, atau (message, code) kalau
    gagal. TIDAK commit — pemanggil yang commit."""
    if order.status == "void":
        return ("Transaksi sudah dibatalkan — tak bisa diedit.", "bad_status")
    EDITABLE = ("product", "ticket")
    parsed = []
    for it in (new_items or []):
        name = (it.get("name") or "").strip()
        try:
            qty = float(it.get("quantity") or it.get("qty") or 0)
            price = float(it.get("unit_price") or 0)
        except (TypeError, ValueError):
            return ("Qty/harga tidak valid.", "bad_item")
        if not name or qty <= 0 or price < 0:
            return ("Baris tidak valid (nama, qty > 0, harga >= 0).", "bad_item")
        itype = it.get("item_type") if it.get("item_type") in EDITABLE else "product"
        parsed.append((itype, it.get("product_id"), name, qty, price))

    old_total = float(order.total_amount or 0)
    non_editable = [it for it in order.items if it.item_type not in EDITABLE]
    non_editable_sum = sum(float(it.line_total or 0) for it in non_editable)
    for it in list(order.items):
        if it.item_type in EDITABLE:
            order.items.remove(it)
    edit_sum = 0.0
    for (itype, product_id, name, qty, price) in parsed:
        line = qty * price
        edit_sum += line
        order.items.append(OrderItem(
            item_type=itype, product_id=product_id, name_snapshot=name[:120],
            unit_price=price, quantity=qty, line_total=line, created_at=order.created_at,
        ))
    subtotal = non_editable_sum + edit_sum
    discount = float(order.discount_amount or 0)
    new_total = round(subtotal - discount, 2)
    if new_total < 0:
        return ("Total menjadi negatif — periksa harga/diskon.", "bad_total")
    order.subtotal = subtotal
    order.total_amount = new_total
    delta = round(new_total - old_total, 2)

    paid = [p for p in order.payments if p.status == "paid"]
    if paid and abs(delta) > 0.005:
        p = paid[-1]
        new_amt = round(float(p.amount) + delta, 2)
        if new_amt < 0:
            return ("Perubahan membuat pembayaran negatif. Untuk mengurangi besar, batalkan transaksi lalu input ulang.", "payment_negative")
        p.amount = new_amt
        if p.shift_id:
            sh = db.session.get(Shift, p.shift_id)
            if sh:
                sh.total_sales = float(sh.total_sales or 0) + delta
                if p.method == "cash":
                    sh.total_cash_sales = float(sh.total_cash_sales or 0) + delta
                elif p.method == "qris":
                    sh.total_qris_sales = float(sh.total_qris_sales or 0) + delta
                elif p.method == "transfer":
                    sh.total_transfer_sales = float(sh.total_transfer_sales or 0) + delta
                sh.expected_cash = (
                    float(sh.opening_cash or 0) + float(sh.total_cash_sales or 0)
                    + float(sh.cash_in or 0) - float(sh.cash_out or 0)
                )
                if sh.counted_cash is not None:
                    sh.cash_variance = float(sh.counted_cash) - float(sh.expected_cash)
    order.amount_paid = round(sum(float(p.amount) for p in order.payments if p.status == "paid"), 2)
    if order.status != "void":
        order.status = "paid" if (new_total > 0 and order.amount_paid >= new_total - 0.005) else "open"
    order.updated_at = datetime.utcnow()
    return None


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
        # Balikkan efek pembayaran PER-shift:
        # - shift masih BUKA  → kurangi akumulasi shift & tandai payment 'void'.
        # - shift sudah DITUTUP → JANGAN diubah (kas historis sudah direkonsiliasi/
        #   disetor). Pembayaran dibiarkan 'paid' → jadi pendapatan/DP hangus yg
        #   tetap tercatat; ordernya tetap bisa dibatalkan lalu dihapus permanen
        #   (jejak DP hangus muncul di tab DP Hangus & Riwayat Hapus).
        for p in paid_payments:
            shift = db.session.get(Shift, p.shift_id) if p.shift_id else None
            if shift and shift.status == "closed":
                continue  # historis — biarkan apa adanya (pendapatan hangus)
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
