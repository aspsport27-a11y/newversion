"""Endpoint POS — Fase M1. Prefix: /api/pos"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from ..extensions import db
from ..models import User
from ..security import verify_password
from .models import Facility, FacilityBooking, PosTerminal, Product, Shift
from .services import (
    PosError,
    add_cash_movement,
    cancel_order,
    close_shift,
    create_order,
    open_shift,
    pay_order,
)

pos_bp = Blueprint("pos", __name__)


@pos_bp.errorhandler(PosError)
def _handle_pos_error(e: PosError):
    return jsonify(error=e.code, message=e.message), e.status


def _claims():
    return get_jwt()


def _current_terminal() -> PosTerminal:
    tid = _claims().get("terminal_id")
    terminal = db.session.get(PosTerminal, tid) if tid else None
    if terminal is None:
        raise PosError("Terminal tidak valid pada token", "no_terminal", 401)
    return terminal


def _current_open_shift(terminal_id: int) -> Shift:
    shift = Shift.query.filter_by(terminal_id=terminal_id, status="open").first()
    if shift is None:
        raise PosError("Belum ada shift terbuka. Buka shift dulu.", "no_open_shift", 409)
    return shift


# ------------------------------------------------------------------
# Auth POS — login PIN + terminal
# ------------------------------------------------------------------
@pos_bp.post("/auth/login")
def pos_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    pin = data.get("pin") or ""
    terminal_code = (data.get("terminal_code") or "").strip()

    if not username or not pin or not terminal_code:
        return jsonify(error="bad_request", message="username, pin, terminal_code wajib"), 400

    terminal = PosTerminal.query.filter_by(code=terminal_code, is_active=True).first()
    if terminal is None:
        return jsonify(error="terminal_not_found", message="Terminal tidak ditemukan/nonaktif"), 404

    user = User.query.filter_by(username=username, active=True).first()
    if user is None or not user.pin_hash or not verify_password(pin, user.pin_hash):
        return jsonify(error="unauthorized", message="Username atau PIN salah"), 401

    # kalau kasir dibatasi venue, harus cocok dengan venue terminal
    if user.venue_id and user.venue_id != terminal.venue_id:
        return jsonify(error="forbidden", message="Kasir tidak berhak di venue terminal ini"), 403

    user.touch_login()
    db.session.commit()

    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "role": user.role,
            "username": user.username,
            "scope": "pos",
            "terminal_id": terminal.id,
            "venue_id": terminal.venue_id,
        },
    )
    return jsonify(
        access_token=token,
        cashier={"id": user.id, "username": user.username, "role": user.role},
        terminal=terminal.to_dict(),
    ), 200


@pos_bp.get("/me")
@jwt_required()
def pos_me():
    terminal = _current_terminal()
    shift = Shift.query.filter_by(terminal_id=terminal.id, status="open").first()
    return jsonify(
        cashier_id=int(get_jwt_identity()),
        username=_claims().get("username"),
        terminal=terminal.to_dict(),
        open_shift=shift.to_dict() if shift else None,
    ), 200


# ------------------------------------------------------------------
# Produk (katalog venue terminal)
# ------------------------------------------------------------------
@pos_bp.get("/products")
@jwt_required()
def pos_products():
    terminal = _current_terminal()
    products = (
        Product.query.filter_by(venue_id=terminal.venue_id, is_active=True)
        .order_by(Product.name)
        .all()
    )
    return jsonify(count=len(products), products=[p.to_dict() for p in products]), 200


# ------------------------------------------------------------------
# Lapangan (facilities) & jadwal — M2
# ------------------------------------------------------------------
@pos_bp.get("/facilities")
@jwt_required()
def pos_facilities():
    terminal = _current_terminal()
    facilities = (
        Facility.query.filter_by(venue_id=terminal.venue_id, is_active=True)
        .order_by(Facility.name)
        .all()
    )
    return jsonify(count=len(facilities), facilities=[f.to_dict() for f in facilities]), 200


@pos_bp.get("/facilities/<int:facility_id>/bookings")
@jwt_required()
def pos_facility_bookings(facility_id):
    """Booking pada 1 lapangan di tanggal tertentu (untuk cek ketersediaan)."""
    terminal = _current_terminal()
    facility = db.session.get(Facility, facility_id)
    if facility is None or facility.venue_id != terminal.venue_id:
        raise PosError("Lapangan tidak ditemukan", "not_found", 404)
    day = request.args.get("date")
    q = FacilityBooking.query.filter_by(facility_id=facility_id, status="booked")
    if day:
        q = q.filter_by(booking_date=day)
    bookings = q.order_by(FacilityBooking.start_time).all()
    return jsonify(
        facility=facility.to_dict(),
        bookings=[b.to_dict() for b in bookings],
    ), 200


# ------------------------------------------------------------------
# Shift
# ------------------------------------------------------------------
@pos_bp.post("/shifts/open")
@jwt_required()
def shift_open():
    terminal = _current_terminal()
    data = request.get_json(silent=True) or {}
    shift = open_shift(
        terminal_id=terminal.id,
        venue_id=terminal.venue_id,
        cashier_id=int(get_jwt_identity()),
        opening_cash=data.get("opening_cash", 0),
    )
    return jsonify(shift=shift.to_dict()), 201


@pos_bp.get("/shifts/current")
@jwt_required()
def shift_current():
    terminal = _current_terminal()
    shift = Shift.query.filter_by(terminal_id=terminal.id, status="open").first()
    return jsonify(shift=shift.to_dict() if shift else None), 200


@pos_bp.post("/shifts/close")
@jwt_required()
def shift_close():
    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    data = request.get_json(silent=True) or {}
    if "counted_cash" not in data:
        raise PosError("counted_cash wajib diisi", "bad_request")
    shift = close_shift(
        shift,
        counted_cash=data.get("counted_cash"),
        deposit_amount=data.get("deposit_amount"),
        notes=data.get("notes"),
    )
    return jsonify(shift=shift.to_dict()), 200


@pos_bp.post("/shifts/cash-movement")
@jwt_required()
def shift_cash_movement():
    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    data = request.get_json(silent=True) or {}
    add_cash_movement(
        shift,
        mtype=data.get("type"),
        amount=data.get("amount", 0),
        reason=data.get("reason"),
        user_id=int(get_jwt_identity()),
    )
    return jsonify(shift=shift.to_dict()), 201


# ------------------------------------------------------------------
# Order & pembayaran
# ------------------------------------------------------------------
@pos_bp.post("/orders")
@jwt_required()
def order_create():
    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    data = request.get_json(silent=True) or {}
    order = create_order(shift, int(get_jwt_identity()), data)
    db.session.commit()
    return jsonify(order=order.to_dict()), 201


@pos_bp.get("/orders/outstanding")
@jwt_required()
def orders_outstanding():
    """Booking/order yang belum lunas (DP) di venue terminal — untuk pelunasan."""
    from .models import Order

    terminal = _current_terminal()
    orders = (
        Order.query.filter_by(venue_id=terminal.venue_id, status="partial")
        .order_by(Order.created_at.desc())
        .all()
    )
    return jsonify(count=len(orders), orders=[o.to_dict() for o in orders]), 200


@pos_bp.get("/orders/<int:order_id>")
@jwt_required()
def order_get(order_id):
    from .models import Order

    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    return jsonify(order=order.to_dict()), 200


@pos_bp.post("/orders/<int:order_id>/pay")
@jwt_required()
def order_pay(order_id):
    from .models import Order

    terminal = _current_terminal()
    shift = _current_open_shift(terminal.id)
    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    if order.venue_id != terminal.venue_id:
        raise PosError("Order bukan milik venue ini", "wrong_venue", 403)
    data = request.get_json(silent=True) or {}
    payment = pay_order(order, shift, int(get_jwt_identity()), data)
    return jsonify(order=order.to_dict(), payment=payment.to_dict()), 200


@pos_bp.post("/orders/<int:order_id>/cancel")
@jwt_required()
def order_cancel(order_id):
    from .models import Order

    terminal = _current_terminal()
    order = db.session.get(Order, order_id)
    if order is None:
        raise PosError("Order tidak ditemukan", "not_found", 404)
    if order.venue_id != terminal.venue_id:
        raise PosError("Order bukan milik venue ini", "wrong_venue", 403)
    cancel_order(order)
    return jsonify(order=order.to_dict()), 200
