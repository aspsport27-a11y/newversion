"""Utilitas keamanan: hashing password (bcrypt) + decorator role."""
from functools import wraps

import bcrypt
from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request

# Role yang dikenal sistem (sesuai desain)
ROLE_ADMIN = "admin"
ROLE_HEAD_OFFICE = "head_office"
ROLE_MANAGER = "manager_unit"
ROLE_STAFF = "staff"
VALID_ROLES = {ROLE_ADMIN, ROLE_HEAD_OFFICE, ROLE_MANAGER, ROLE_STAFF}


def hash_password(password: str) -> str:
    """Hash password dengan bcrypt, kembalikan string siap simpan ke password_hash."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verifikasi password terhadap hash tersimpan."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def roles_required(*roles):
    """Batasi akses endpoint hanya untuk role tertentu."""

    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get("role") not in roles:
                return (
                    jsonify(error="forbidden", message="Role tidak diizinkan"),
                    403,
                )
            return fn(*args, **kwargs)

        return decorated

    return wrapper
