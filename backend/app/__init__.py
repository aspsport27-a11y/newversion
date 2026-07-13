"""Application factory untuk backend ASP Sport / Venue Management System."""
import click
from flask import Flask, jsonify

from .config import Config
from .extensions import cors, db, jwt, migrate
from .security import VALID_ROLES

# Blocklist token in-memory (untuk logout). Untuk multi-worker/produksi
# sebaiknya dipindah ke Redis; cukup untuk Fase 1.
TOKEN_BLOCKLIST: set[str] = set()


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ekstensi
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    # register model agar dikenali SQLAlchemy/Flask-Migrate
    from . import models  # noqa: F401
    from .ops import models as ops_models  # noqa: F401
    from .payroll import models as payroll_models  # noqa: F401
    from .pos import models as pos_models  # noqa: F401
    from .proc import models as proc_models  # noqa: F401
    from .treasury import models as treasury_models  # noqa: F401

    # blueprint
    from .admin.routes import admin_bp
    from .auth.routes import auth_bp
    from .financial.routes import financial_bp
    from .main.routes import main_bp
    from .ops.routes import ops_bp
    from .payroll.routes import payroll_bp
    from .pos.routes import pos_bp
    from .proc.routes import proc_bp
    from .treasury.routes import treasury_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(main_bp, url_prefix="/api")
    app.register_blueprint(pos_bp, url_prefix="/api/pos")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(ops_bp, url_prefix="/api/ops")
    app.register_blueprint(proc_bp, url_prefix="/api/procurement")
    app.register_blueprint(payroll_bp, url_prefix="/api/payroll")
    app.register_blueprint(treasury_bp, url_prefix="/api/treasury")
    app.register_blueprint(financial_bp, url_prefix="/api/financial")

    _register_jwt_handlers(app)
    _register_error_handlers(app)
    _register_cli(app)

    from .pos.cli import register_pos_cli

    register_pos_cli(app)
    return app


def _register_jwt_handlers(app: Flask) -> None:
    @jwt.token_in_blocklist_loader
    def _check_revoked(_jwt_header, jwt_payload):
        return jwt_payload["jti"] in TOKEN_BLOCKLIST

    @jwt.revoked_token_loader
    def _revoked(_h, _p):
        return jsonify(error="token_revoked", message="Token sudah dicabut"), 401

    @jwt.expired_token_loader
    def _expired(_h, _p):
        return jsonify(error="token_expired", message="Token kedaluwarsa"), 401

    @jwt.unauthorized_loader
    def _missing(reason):
        return jsonify(error="authorization_required", message=reason), 401

    @jwt.invalid_token_loader
    def _invalid(reason):
        return jsonify(error="invalid_token", message=reason), 422


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def _not_found(_e):
        return jsonify(error="not_found", message="Endpoint tidak ditemukan"), 404

    @app.errorhandler(405)
    def _method(_e):
        return jsonify(error="method_not_allowed", message="Metode tidak diizinkan"), 405

    @app.errorhandler(500)
    def _server(_e):
        db.session.rollback()
        return jsonify(error="server_error", message="Terjadi kesalahan server"), 500


def _register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--username", required=True)
    @click.option("--email", required=True)
    @click.option("--password", required=True)
    @click.option("--role", default="admin", show_default=True)
    def create_admin(username, email, password, role):
        """Buat user baru (default role admin)."""
        from .models import User

        if role not in VALID_ROLES:
            raise click.ClickException(
                f"Role tidak valid. Pilihan: {', '.join(sorted(VALID_ROLES))}"
            )
        if User.query.filter(
            (User.username == username) | (User.email == email)
        ).first():
            raise click.ClickException("Username atau email sudah dipakai.")
        if len(password) < 8:
            raise click.ClickException("Password minimal 8 karakter.")

        user = User(username=username, email=email, role=role, active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"✅ User '{username}' (role={role}) dibuat dengan id={user.id}")
