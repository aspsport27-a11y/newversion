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
    # jenis station (mis. "Ruangan VIP", "Simulator PS") — dasar RESERVASI:
    # customer pesan jenisnya, unit ditentukan saat datang. Lihat migrasi 050.
    station_type = db.Column(db.String(50))
    hourly_rate = db.Column(db.Numeric(15, 2), nullable=False, default=0)  # tarif weekday
    weekend_rate = db.Column(db.Numeric(15, 2))  # tarif akhir pekan/libur; NULL = pakai hourly_rate
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sessions = db.relationship("GameSession", backref="station", lazy="selectin")

    def rate_for(self, weekend: bool) -> float:
        """Tarif berlaku: weekend_rate bila akhir pekan & terisi, else hourly_rate."""
        if weekend and self.weekend_rate is not None:
            return float(self.weekend_rate)
        return float(self.hourly_rate or 0)

    def to_dict(self, active_session=None, weekend=False):
        return {
            "id": self.id, "venue_id": self.venue_id, "code": self.code, "name": self.name,
            "tier": self.tier, "station_type": self.station_type,
            "hourly_rate": float(self.hourly_rate or 0),
            "weekend_rate": float(self.weekend_rate) if self.weekend_rate is not None else None,
            "today_rate": self.rate_for(weekend), "is_active": self.is_active,
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
    # paket waktu awal (menit) yg dipesan customer saat mulai — sewa station
    # ditagih FIX dari sini (jam dipesan x tarif), bukan per menit terpakai.
    # 0 = sesi lama sebelum fitur ini (fallback ke perhitungan elapsed).
    booked_minutes = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)  # dibuat/dibayar
    play_started_at = db.Column(db.DateTime)  # mulai MAIN (klik Play); NULL = belum dimainkan
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
    fnb_items = db.relationship(
        "GameSessionFnb", backref="session", lazy="selectin", cascade="all, delete-orphan",
        order_by="GameSessionFnb.id",
    )

    def elapsed_minutes(self):
        end = self.stopped_at or datetime.utcnow()
        return max(0, int((end - self.started_at).total_seconds() // 60))

    def _is_legacy(self):
        """Sesi lama sebelum fitur paket tetap (booked_minutes 0/None) →
        tetap pakai perhitungan per-menit elapsed spt dulu."""
        return not self.booked_minutes or int(self.booked_minutes) <= 0

    def allocated_minutes(self):
        """Total waktu yg SUDAH dibayar = paket awal + semua tambah waktu.
        Sumber angka hitung mundur di layar."""
        return int(self.booked_minutes or 0) + sum(int(t.duration_minutes) for t in self.topups)

    def time_charge(self):
        # Sewa station = harga FIX paket awal (jam dipesan x tarif), BUKAN per
        # menit terpakai. Sesi lama fallback ke elapsed (perilaku lama).
        minutes = self.elapsed_minutes() if self._is_legacy() else int(self.booked_minutes)
        return round(minutes / 60 * float(self.rate_per_hour), 2)

    def topup_charge(self):
        return round(sum(float(t.total_amount) for t in self.topups), 2)

    def _billable_minutes(self):
        """Durasi dasar utk hitung add-on: ikut waktu yg dibayar (paket +
        tambah waktu) supaya harga tetap/fix; sesi lama ikut elapsed."""
        return self.elapsed_minutes() if self._is_legacy() else self.allocated_minutes()

    def addon_charge(self):
        # add-on PRABAYAR (booked_minutes>0) sudah dibayar saat ditempel → tak
        # dihitung lagi di stop. Add-on LAMA (booked_minutes 0) ikut durasi sesi.
        minutes = self._billable_minutes()
        return round(sum(
            minutes / 60 * float(a.rate_per_hour) * a.quantity
            for a in self.addons if not (a.booked_minutes and a.booked_minutes > 0)
        ), 2)

    def fnb_charge(self):
        return round(sum(float(f.unit_price) * f.quantity for f in self.fnb_items), 2)

    def total_charge(self):
        return round(
            self.time_charge() + self.topup_charge() + self.addon_charge() + self.fnb_charge(), 2
        )

    def to_dict(self):
        return {
            "id": self.id, "station_id": self.station_id, "customer_name": self.customer_name,
            "rate_per_hour": float(self.rate_per_hour),
            "booked_minutes": int(self.booked_minutes or 0),
            "allocated_minutes": self.allocated_minutes(),
            "started_at": (self.started_at.isoformat() + "Z") if self.started_at else None,
            "play_started_at": (self.play_started_at.isoformat() + "Z") if self.play_started_at else None,
            "playing": self.play_started_at is not None,
            "status": self.status,
            "stopped_at": (self.stopped_at.isoformat() + "Z") if self.stopped_at else None,
            "elapsed_minutes": self.elapsed_minutes(),
            "time_charge": self.time_charge(),
            "topup_charge": self.topup_charge(),
            "addon_charge": self.addon_charge(),
            "fnb_charge": self.fnb_charge(),
            "total_charge": self.total_charge(),
            "order_id": self.order_id,
            "topups": [t.to_dict() for t in self.topups],
            "addons": [a.to_dict() for a in self.addons],
            "fnb_items": [f.to_dict() for f in self.fnb_items],
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
    # PRABAYAR + timer sendiri: durasi sewa add-on (terpisah dari station).
    # 0 = add-on lama (ikut durasi sesi & ditagih di stop).
    booked_minutes = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime)
    total_amount = db.Column(db.Numeric(15, 2))  # biaya prabayar (kalau booked_minutes>0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "addon_id": self.addon_id, "name": self.name_snapshot,
            "rate_per_hour": float(self.rate_per_hour), "quantity": self.quantity,
            "booked_minutes": int(self.booked_minutes or 0),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "total_amount": float(self.total_amount) if self.total_amount is not None else None,
            "prepaid": bool(self.booked_minutes and self.booked_minutes > 0),
        }


class GameSessionFnb(db.Model):
    """F&B yg dipesan customer di tengah sesi (dientry kasir biar tak lupa,
    dibayar sekalian saat stop). unit_price DISALIN saat dientry (snapshot);
    total final tetap dihitung ulang di create_order saat stop (item_type
    'product', jadi promo & potong stok ditangani kanonik di sana)."""
    __tablename__ = "game_session_fnb"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    name_snapshot = db.Column(db.String(120), nullable=False)
    unit_price = db.Column(db.Numeric(15, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "product_id": self.product_id, "name": self.name_snapshot,
            "unit_price": float(self.unit_price), "quantity": self.quantity,
            "line_total": round(float(self.unit_price) * self.quantity, 2),
        }


class StationReservation(db.Model):
    """Reservasi station di muka — yg dipesan JENIS station, bukan unit tertentu.

    Alasannya: sesi station tak punya akhir pasti (bisa "tambah waktu"), jadi
    mengunci unit tertentu terlalu rapuh. Dgn per-jenis, bentrok baru terjadi
    kalau SEMUA unit jenis itu terpakai. Unit ditentukan saat customer datang.
    Uangnya nempel di `order_id` (prabayar, pola sama dgn station_start).
    """

    __tablename__ = "station_reservations"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    station_type = db.Column(db.String(50), nullable=False)
    reservation_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="SET NULL"))
    status = db.Column(db.String(12), nullable=False, default="booked")  # booked|fulfilled|cancelled
    station_id = db.Column(db.Integer, db.ForeignKey("game_stations.id", ondelete="SET NULL"))
    session_id = db.Column(db.Integer, db.ForeignKey("game_sessions.id", ondelete="SET NULL"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        hm = lambda t: t.strftime("%H:%M") if t else None
        return {
            "id": self.id,
            "venue_id": self.venue_id,
            "station_type": self.station_type,
            "date": self.reservation_date.isoformat() if self.reservation_date else None,
            "start_time": hm(self.start_time),
            "end_time": hm(self.end_time),
            "duration_minutes": self.duration_minutes,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "order_id": self.order_id,
            "status": self.status,
            "station_id": self.station_id,
            "session_id": self.session_id,
        }


def _resv_mins(t, as_end=False):
    """Jam → menit; 00:00 sbg akhir rentang = jam ke-24 (konvensi sama dgn jam
    tutup lapangan, lihat HANDOVER §9)."""
    m = t.hour * 60 + t.minute
    return 24 * 60 if (as_end and m == 0) else m


def station_type_usage(venue_id, station_type, d, start, end, exclude_id=None):
    """(kapasitas, terpakai, rincian) utk satu jenis station pada slot [start,end).

    'terpakai' = reservasi lain yg tumpang tindih + sesi yg SEDANG BERJALAN di
    unit jenis itu yg diperkirakan masih jalan saat slot tsb. Perkiraan akhir
    sesi = mulai main + total waktu yg sudah dibayar (paket + tambah waktu);
    memang perkiraan, karena customer bisa menambah waktu lagi kapan saja —
    itulah kenapa reservasi dibuat per-jenis, bukan per-unit.
    """
    from datetime import date as _date, datetime as _dt, timedelta as _td

    units = GameStation.query.filter_by(
        venue_id=venue_id, station_type=station_type, is_active=True
    ).all()
    capacity = len(units)
    s_min, e_min = _resv_mins(start), _resv_mins(end, as_end=True)

    q = StationReservation.query.filter_by(
        venue_id=venue_id, station_type=station_type,
        reservation_date=d, status="booked",
    )
    if exclude_id:
        q = q.filter(StationReservation.id != exclude_id)
    used_resv = sum(
        1 for r in q.all()
        if _resv_mins(r.start_time) < e_min and _resv_mins(r.end_time, as_end=True) > s_min
    )

    # sesi berjalan hanya relevan kalau reservasinya utk HARI INI
    used_live = 0
    if units and d == _date.today():
        unit_ids = [u.id for u in units]
        for sess in GameSession.query.filter(
            GameSession.station_id.in_(unit_ids), GameSession.status == "ongoing"
        ).all():
            anchor = sess.play_started_at or sess.started_at
            if anchor is None:
                continue
            est_end = anchor + _td(minutes=sess.allocated_minutes())
            a_min = anchor.hour * 60 + anchor.minute
            b_min = a_min + max(0, int((est_end - anchor).total_seconds() // 60))
            if a_min < e_min and b_min > s_min:
                used_live += 1

    return capacity, used_resv + used_live, {"reservasi": used_resv, "sesi_berjalan": used_live}


def topup_reservation_warning(session, station, station_type=None):
    """Peringatan (string) kalau sesi ini — SETELAH diperpanjang — melewati
    reservasi jenis yg sama sampai kapasitasnya terlampaui. None = aman.

    Sengaja PERINGATAN, bukan blokir: keputusan user, kasir tetap boleh
    memperpanjang (mis. slot berikutnya ternyata batal atau bisa dialihkan ke
    unit lain). Dipanggil SETELAH topup di-flush, jadi allocated_minutes()
    sudah termasuk tambahan waktunya.
    """
    from datetime import date as _date, datetime as _dt

    stype = station_type or station.station_type
    if not stype:
        return None
    anchor = session.play_started_at or session.started_at
    if anchor is None:
        return None
    today = _date.today()
    if anchor.date() != today:
        return None  # sesi lintas hari — di luar cakupan peringatan ini

    now_min = _dt.utcnow().hour * 60 + _dt.utcnow().minute
    end_min = anchor.hour * 60 + anchor.minute + session.allocated_minutes()

    upcoming = StationReservation.query.filter_by(
        venue_id=session.venue_id, station_type=stype,
        reservation_date=today, status="booked",
    ).order_by(StationReservation.start_time).all()

    for r in upcoming:
        r_start, r_end = _resv_mins(r.start_time), _resv_mins(r.end_time, as_end=True)
        if r_end <= now_min or r_start >= end_min:
            continue  # reservasi sudah lewat, atau sesi ini berakhir sebelum mulai
        cap, used, _d = station_type_usage(
            session.venue_id, stype, today, r.start_time, r.end_time
        )
        if used > cap:
            return (
                f"Perpanjangan ini melewati reservasi {stype} jam "
                f"{r.start_time:%H:%M}–{r.end_time:%H:%M}"
                + (f" a/n {r.customer_name}" if r.customer_name else "")
                + f" — semua {cap} unit akan terpakai. Pastikan sudah dikoordinasikan."
            )
    return None


def reservations_today(venue_id):
    """Reservasi hari ini yg belum dipakai — utk ditampilkan di layar POS."""
    from datetime import date as _date

    rows = (
        StationReservation.query.filter_by(
            venue_id=venue_id, reservation_date=_date.today(), status="booked"
        )
        .order_by(StationReservation.start_time)
        .all()
    )
    return [r.to_dict() for r in rows]
