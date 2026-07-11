"""Perintah CLI untuk menyiapkan data POS (terminal, kasir, produk)."""
import click
from flask import Flask

from ..extensions import db
from ..models import User, Venue
from ..security import hash_password
from .models import PosTerminal, Product, ProductCategory


def _venue_by_code(code):
    venue = Venue.query.filter_by(code=code).first()
    if venue is None:
        raise click.ClickException(f"Venue dengan code '{code}' tidak ditemukan.")
    return venue


def register_pos_cli(app: Flask) -> None:
    @app.cli.command("pos-terminal")
    @click.option("--code", required=True)
    @click.option("--name", required=True)
    @click.option("--venue-code", required=True)
    def create_terminal(code, name, venue_code):
        """Buat terminal POS terikat 1 venue."""
        venue = _venue_by_code(venue_code)
        if PosTerminal.query.filter_by(code=code).first():
            raise click.ClickException("Kode terminal sudah dipakai.")
        t = PosTerminal(code=code, name=name, venue_id=venue.id, is_active=True)
        db.session.add(t)
        db.session.commit()
        click.echo(f"✅ Terminal '{code}' → venue {venue.code} (id={t.id})")

    @app.cli.command("pos-cashier")
    @click.option("--username", required=True)
    @click.option("--email", required=True)
    @click.option("--pin", required=True)
    @click.option("--venue-code", default=None, help="Batasi kasir ke venue ini")
    def create_cashier(username, email, pin, venue_code):
        """Buat user kasir (role staff) dengan PIN."""
        if len(pin) < 4:
            raise click.ClickException("PIN minimal 4 digit.")
        if User.query.filter((User.username == username) | (User.email == email)).first():
            raise click.ClickException("Username/email sudah dipakai.")
        venue_id = _venue_by_code(venue_code).id if venue_code else None
        user = User(username=username, email=email, role="staff", active=True, venue_id=venue_id)
        user.set_password(pin)  # password fallback = pin (bisa diganti)
        user.pin_hash = hash_password(pin)
        db.session.add(user)
        db.session.commit()
        click.echo(f"✅ Kasir '{username}' (id={user.id}, venue={venue_code or 'semua'})")

    @app.cli.command("pos-set-pin")
    @click.option("--username", required=True)
    @click.option("--pin", required=True)
    def set_pin(username, pin):
        """Set/ganti PIN kasir."""
        user = User.query.filter_by(username=username).first()
        if user is None:
            raise click.ClickException("User tidak ditemukan.")
        user.pin_hash = hash_password(pin)
        db.session.commit()
        click.echo(f"✅ PIN '{username}' diperbarui.")

    @app.cli.command("pos-product")
    @click.option("--sku", required=True)
    @click.option("--name", required=True)
    @click.option("--venue-code", required=True)
    @click.option("--price", required=True, type=float)
    @click.option("--stock", default=0, type=int)
    @click.option("--track-stock/--no-track-stock", default=True)
    @click.option("--category", default=None)
    @click.option("--kind", default="other")
    def create_product(sku, name, venue_code, price, stock, track_stock, category, kind):
        """Buat produk untuk venue tertentu."""
        venue = _venue_by_code(venue_code)
        if Product.query.filter_by(sku=sku).first():
            raise click.ClickException("SKU sudah dipakai.")
        cat_id = None
        if category:
            cat = ProductCategory.query.filter_by(name=category).first()
            if cat is None:
                cat = ProductCategory(name=category, kind=kind)
                db.session.add(cat)
                db.session.flush()
            cat_id = cat.id
        p = Product(
            sku=sku, name=name, venue_id=venue.id, price=price,
            stock_qty=stock, track_stock=track_stock, category_id=cat_id, is_active=True,
        )
        db.session.add(p)
        db.session.commit()
        click.echo(f"✅ Produk '{name}' (sku={sku}) venue {venue.code}, harga {price}, stok {stock}")
