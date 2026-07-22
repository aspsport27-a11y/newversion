"""Model SQLAlchemy untuk POS M0 — memetakan tabel migration 002_pos_m0.sql."""
from datetime import datetime

from ..extensions import db


class PosTerminal(db.Model):
    __tablename__ = "pos_terminals"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name,
                "venue_id": self.venue_id, "is_active": self.is_active}


class ProductCategory(db.Model):
    __tablename__ = "product_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="other")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    category_id = db.Column(
        db.Integer, db.ForeignKey("product_categories.id", ondelete="SET NULL")
    )
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    price = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    promo_price = db.Column(db.Numeric(15, 2))
    unit = db.Column(db.String(20), default="pcs")
    track_stock = db.Column(db.Boolean, default=True)
    stock_qty = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=0)  # ambang reorder
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="SET NULL"))
    is_ticket = db.Column(db.Boolean, nullable=False, default=False)  # tiket masuk (waterpark)
    weekend_price = db.Column(db.Numeric(15, 2))  # harga weekend/libur (khusus tiket)
    is_consignment = db.Column(db.Boolean, nullable=False, default=False)  # produk titipan/konsinyasi
    consignment_price = db.Column(db.Numeric(15, 2))  # jumlah tetap ke supplier per unit terjual
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "category_id": self.category_id,
            "venue_id": self.venue_id,
            "price": float(self.price or 0),
            "unit": self.unit,
            "track_stock": self.track_stock,
            "stock_qty": self.stock_qty,
            "min_stock": self.min_stock or 0,
            "supplier_id": self.supplier_id,
            "is_ticket": self.is_ticket,
            "weekend_price": float(self.weekend_price) if self.weekend_price is not None else None,
            "is_consignment": self.is_consignment,
            "consignment_price": float(self.consignment_price) if self.consignment_price is not None else None,
            "is_active": self.is_active,
        }


class Holiday(db.Model):
    """Hari libur nasional — tanggal ini dihitung sebagai 'weekend' utk harga tiket."""
    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "date": self.date.isoformat() if self.date else None, "name": self.name}


class Promo(db.Model):
    __tablename__ = "promos"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    type = db.Column(db.String(10), nullable=False, default="price")  # price|percent|bogo
    promo_price = db.Column(db.Numeric(15, 2))
    percent = db.Column(db.Numeric(5, 2))
    buy_qty = db.Column(db.Integer)
    get_qty = db.Column(db.Integer)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "product_id": self.product_id,
            "type": self.type,
            "promo_price": float(self.promo_price) if self.promo_price is not None else None,
            "percent": float(self.percent) if self.percent is not None else None,
            "buy_qty": self.buy_qty,
            "get_qty": self.get_qty,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
        }


class Facility(db.Model):
    __tablename__ = "facilities"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50))
    hourly_rate = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    open_time = db.Column(db.Time)
    close_time = db.Column(db.Time)
    slot_minutes = db.Column(db.Integer, default=60)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)

    def to_dict(self):
        hm = lambda t: t.strftime("%H:%M") if t else None
        return {
            "id": self.id,
            "venue_id": self.venue_id,
            "name": self.name,
            "type": self.type,
            "hourly_rate": float(self.hourly_rate or 0),
            "open_time": hm(self.open_time),
            "close_time": hm(self.close_time),
            "slot_minutes": self.slot_minutes,
            "is_active": self.is_active,
        }


class Shift(db.Model):
    __tablename__ = "shifts"

    id = db.Column(db.Integer, primary_key=True)
    terminal_id = db.Column(db.Integer, db.ForeignKey("pos_terminals.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    cashier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="open")
    opened_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    opening_cash = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total_cash_sales = db.Column(db.Numeric(15, 2), default=0)
    total_qris_sales = db.Column(db.Numeric(15, 2), default=0)
    total_sales = db.Column(db.Numeric(15, 2), default=0)
    cash_in = db.Column(db.Numeric(15, 2), default=0)
    cash_out = db.Column(db.Numeric(15, 2), default=0)
    expected_cash = db.Column(db.Numeric(15, 2), default=0)
    counted_cash = db.Column(db.Numeric(15, 2))
    cash_variance = db.Column(db.Numeric(15, 2))
    deposit_amount = db.Column(db.Numeric(15, 2))
    deposit_id = db.Column(db.Integer, db.ForeignKey("cash_deposits.id"))  # sudah disetor?
    notes = db.Column(db.Text)

    def to_dict(self):
        f = lambda v: float(v) if v is not None else None
        return {
            "id": self.id,
            "terminal_id": self.terminal_id,
            "venue_id": self.venue_id,
            "cashier_id": self.cashier_id,
            "status": self.status,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "opening_cash": f(self.opening_cash),
            "total_cash_sales": f(self.total_cash_sales),
            "total_qris_sales": f(self.total_qris_sales),
            "total_sales": f(self.total_sales),
            "cash_in": f(self.cash_in),
            "cash_out": f(self.cash_out),
            "expected_cash": f(self.expected_cash),
            "counted_cash": f(self.counted_cash),
            "cash_variance": f(self.cash_variance),
            "deposit_amount": f(self.deposit_amount),
        }


class CashMovement(db.Model):
    __tablename__ = "cash_movements"

    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(
        db.Integer, db.ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    type = db.Column(db.String(4), nullable=False)  # in|out
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    reason = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(30), unique=True, nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    terminal_id = db.Column(db.Integer, db.ForeignKey("pos_terminals.id"))
    shift_id = db.Column(db.Integer, db.ForeignKey("shifts.id"))
    cashier_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    status = db.Column(db.String(10), nullable=False, default="open")  # open|paid|void
    subtotal = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        "OrderItem", backref="order", lazy="selectin", cascade="all, delete-orphan"
    )
    payments = db.relationship(
        "Payment", backref="order", lazy="selectin", cascade="all, delete-orphan"
    )

    def to_dict(self):
        f = lambda v: float(v) if v is not None else None
        total = float(self.total_amount or 0)
        paid = float(self.amount_paid or 0)
        return {
            "id": self.id,
            "order_number": self.order_number,
            "venue_id": self.venue_id,
            "status": self.status,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "subtotal": f(self.subtotal),
            "discount_amount": f(self.discount_amount),
            "total_amount": total,
            "amount_paid": paid,
            "amount_due": round(total - paid, 2),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "items": [i.to_dict() for i in self.items],
            "payments": [p.to_dict() for p in self.payments],
        }


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    item_type = db.Column(db.String(10), nullable=False)  # product|ticket|rental|booking
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    name_snapshot = db.Column(db.String(120), nullable=False)
    unit_price = db.Column(db.Numeric(15, 2), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False, default=1)
    line_total = db.Column(db.Numeric(15, 2), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "item_type": self.item_type,
            "product_id": self.product_id,
            "name": self.name_snapshot,
            "unit_price": float(self.unit_price),
            "quantity": float(self.quantity),
            "line_total": float(self.line_total),
        }


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    method = db.Column(db.String(10), nullable=False)  # cash|qris
    provider = db.Column(db.String(30), nullable=False, default="cash")
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="pending")  # pending|paid|failed|void
    reference = db.Column(db.String(100))
    confirmed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    shift_id = db.Column(db.Integer, db.ForeignKey("shifts.id"))
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "method": self.method,
            "provider": self.provider,
            "amount": float(self.amount),
            "status": self.status,
            "reference": self.reference,
            "shift_id": self.shift_id,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
        }


class FacilityBooking(db.Model):
    __tablename__ = "facility_bookings"

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey("facilities.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    order_item_id = db.Column(
        db.Integer, db.ForeignKey("order_items.id", ondelete="SET NULL")
    )
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="booked")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        hm = lambda t: t.strftime("%H:%M") if t else None
        return {
            "id": self.id,
            "facility_id": self.facility_id,
            "booking_date": self.booking_date.isoformat() if self.booking_date else None,
            "start_time": hm(self.start_time),
            "end_time": hm(self.end_time),
            "status": self.status,
        }


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    type = db.Column(db.String(12), nullable=False)  # sale|purchase|adjustment|return
    quantity = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer)
    reference = db.Column(db.String(50))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Attendance(db.Model):
    """Kehadiran staff — absen masuk/pulang via terminal POS (rekap saja).
    1 baris per user per hari (UNIQUE user_id+date)."""
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="SET NULL"))
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"))
    terminal_id = db.Column(db.Integer, db.ForeignKey("pos_terminals.id", ondelete="SET NULL"))
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    check_in_photo = db.Column(db.String(255))
    check_out_photo = db.Column(db.String(255))
    # "lat,lon" dari geolocation browser saat absen — verifikasi absen dilakukan di luar/lokasi venue
    check_in_location = db.Column(db.String(100))
    check_out_location = db.Column(db.String(100))
    # alamat hasil reverse geocoding (Nominatim/OSM), disimpan sekali saat absen
    check_in_address = db.Column(db.String(255))
    check_out_address = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "date"),)

    def to_dict(self, name=None):
        hm = lambda t: t.strftime("%H:%M") if t else None
        dur = None
        if self.check_in and self.check_out:
            dur = round((self.check_out - self.check_in).total_seconds() / 3600, 2)
        return {
            "id": self.id, "user_id": self.user_id, "employee_id": self.employee_id,
            "venue_id": self.venue_id, "name": name,
            "date": self.date.isoformat() if self.date else None,
            "check_in": hm(self.check_in), "check_out": hm(self.check_out),
            "work_hours": dur,
            "has_in_photo": bool(self.check_in_photo),
            "has_out_photo": bool(self.check_out_photo),
            "check_in_location": self.check_in_location,
            "check_out_location": self.check_out_location,
            "check_in_address": self.check_in_address,
            "check_out_address": self.check_out_address,
        }
