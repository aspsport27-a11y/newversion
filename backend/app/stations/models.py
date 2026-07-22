"""Model Station Gaming (arena esport) — sewa per stasiun dgn timer berjalan.

Station = data master (spt Facility, tapi utk PS/PC/simulator), punya tier
krn tarif beda2. Session = 1 kali main (start s/d stop); rate_per_hour
DISALIN dari station saat start supaya perubahan tarif nanti tak mengubah
sesi yg sudah/sedang berjalan. Status station TIDAK disimpan sbg kolom —
dihitung dari ada/tidaknya sesi 'ongoing' pada station itu (lihat to_dict).
"""
from datetime import datetime

from ..extensions import db

TIERS = ("reguler", "vip", "simulator")


class GameStation(db.Model):
    __tablename__ = "game_stations"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    tier = db.Column(db.String(20), nullable=False, default="reguler")
    hourly_rate = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sessions = db.relationship("GameSession", backref="station", lazy="selectin")

    def to_dict(self, active_session=None):
        return {
            "id": self.id, "venue_id": self.venue_id, "code": self.code, "name": self.name,
            "tier": self.tier, "hourly_rate": float(self.hourly_rate or 0), "is_active": self.is_active,
            "status": "ongoing" if active_session else "ready",
            "session": active_session.to_dict() if active_session else None,
        }


class GameSession(db.Model):
    __tablename__ = "game_sessions"

    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.Integer, db.ForeignKey("game_stations.id", ondelete="CASCADE"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    customer_name = db.Column(db.String(100))
    rate_per_hour = db.Column(db.Numeric(15, 2), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(12), nullable=False, default="ongoing")  # ongoing|stopped
    stopped_at = db.Column(db.DateTime)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="SET NULL"))
    opened_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    topups = db.relationship(
        "GameSessionTopup", backref="session", lazy="selectin", cascade="all, delete-orphan",
        order_by="GameSessionTopup.id",
    )
    addons = db.relationship(
        "GameSessionAddon", backref="session", lazy="selectin", cascade="all, delete-orphan",
        order_by="GameSessionAddon.id",
    )

    def elapsed_minutes(self):
        end = self.stopped_at or datetime.utcnow()
        return max(0, int((end - self.started_at).total_seconds() // 60))

    def time_charge(self):
        return round(self.elapsed_minutes() / 60 * float(self.rate_per_hour), 2)

    def topup_charge(self):
        return round(sum(float(t.total_amount) for t in self.topups), 2)

    def addon_charge(self):
        # add-on ditagih per jam MENGIKUTI durasi sesi utama (bukan waktu sendiri)
        minutes = self.elapsed_minutes()
        return round(sum(minutes / 60 * float(a.rate_per_hour) * a.quantity for a in self.addons), 2)

    def total_charge(self):
        return round(self.time_charge() + self.topup_charge() + self.addon_charge(), 2)

    def to_dict(self):
        return {
            "id": self.id, "station_id": self.station_id, "customer_name": self.customer_name,
            "rate_per_hour": float(self.rate_per_hour),
            "started_at": (self.started_at.isoformat() + "Z") if self.started_at else None,
            "status": self.status,
            "stopped_at": (self.stopped_at.isoformat() + "Z") if self.stopped_at else None,
            "elapsed_minutes": self.elapsed_minutes(),
            "time_charge": self.time_charge(),
            "topup_charge": self.topup_charge(),
            "addon_charge": self.addon_charge(),
            "total_charge": self.total_charge(),
            "order_id": self.order_id,
            "topups": [t.to_dict() for t in self.topups],
            "addons": [a.to_dict() for a in self.addons],
        }


class GameSessionTopup(db.Model):
    __tablename__ = "game_session_topups"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    discount_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(15, 2), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "duration_minutes": self.duration_minutes,
            "discount_amount": float(self.discount_amount or 0), "total_amount": float(self.total_amount),
            "created_at": (self.created_at.isoformat() + "Z") if self.created_at else None,
        }


class GameAddon(db.Model):
    """Katalog perangkat tambahan (stick ekstra, VR, setir racing dll) per
    venue — ditagih per jam mengikuti durasi sesi utama (lihat GameSession.addon_charge)."""
    __tablename__ = "game_addons"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    hourly_rate = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "venue_id": self.venue_id, "name": self.name,
            "hourly_rate": float(self.hourly_rate or 0), "is_active": self.is_active,
        }


class GameSessionAddon(db.Model):
    """Add-on yg ditempelkan ke satu sesi. rate_per_hour DISALIN dari GameAddon
    saat ditempelkan (sama pola dgn GameSession.rate_per_hour) spy perubahan
    tarif katalog nanti tak mengubah sesi yg sudah/sedang berjalan."""
    __tablename__ = "game_session_addons"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False)
    addon_id = db.Column(db.Integer, db.ForeignKey("game_addons.id"), nullable=False)
    name_snapshot = db.Column(db.String(100), nullable=False)
    rate_per_hour = db.Column(db.Numeric(15, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "addon_id": self.addon_id, "name": self.name_snapshot,
            "rate_per_hour": float(self.rate_per_hour), "quantity": self.quantity,
        }
