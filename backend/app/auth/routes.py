"""Endpoint autentikasi — Fase 1."""
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from ..extensions import db
from ..models import User

auth_bp = Blueprint("auth", __name__)


def _token_for(user: User):
    """Buat access + refresh token dengan klaim tambahan (role, username)."""
    claims = {"role": user.role, "username": user.username}
    identity = str(user.id)
    return (
        create_access_token(identity=identity, additional_claims=claims),
        create_refresh_token(identity=identity, additional_claims=claims),
    )


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get("username") or data.get("email") or "").strip()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify(error="bad_request", message="username/email dan password wajib diisi"), 400

    user = User.query.filter(
        (User.username == identifier) | (User.email == identifier)
    ).first()

    if user is None or not user.check_password(password):
        return jsonify(error="unauthorized", message="Kredensial salah"), 401
    if not user.active:
        return jsonify(error="forbidden", message="Akun nonaktif"), 403
    if user.role not in ("admin", "head_office", "manager_unit", "admin_unit"):
        return jsonify(
            error="forbidden",
            message="Akun ini tidak diizinkan login di portal. Gunakan POS untuk login kasir.",
        ), 403

    user.touch_login()
    db.session.commit()

    access, refresh = _token_for(user)
    from ..perms import perms_for_role
    return jsonify(
        access_token=access,
        refresh_token=refresh,
        user=user.to_dict(),
        permissions=perms_for_role(user.role),
    ), 200


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.active:
        return jsonify(error="unauthorized", message="User tidak valid"), 401
    access = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "username": user.username},
    )
    return jsonify(access_token=access), 200


@auth_bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return jsonify(error="not_found", message="User tidak ditemukan"), 404
    from ..perms import perms_for_role
    return jsonify(user=user.to_dict(), permissions=perms_for_role(user.role)), 200


@auth_bp.post("/logout")
@jwt_required()
def logout():
    """Cabut token akses saat ini (masuk blocklist in-memory)."""
    jti = get_jwt()["jti"]
    from .. import TOKEN_BLOCKLIST

    TOKEN_BLOCKLIST.add(jti)
    return jsonify(message="Logout berhasil"), 200


@auth_bp.post("/reset-password")
@jwt_required()
def reset_password():
    """Ganti password user yang sedang login (butuh password lama)."""
    data = request.get_json(silent=True) or {}
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if len(new_password) < 8:
        return jsonify(error="bad_request", message="Password baru minimal 8 karakter"), 400

    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.check_password(old_password):
        return jsonify(error="unauthorized", message="Password lama salah"), 401

    user.set_password(new_password)
    user.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(message="Password berhasil diganti"), 200
