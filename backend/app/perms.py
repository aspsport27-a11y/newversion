"""RBAC configurable — katalog izin + akses matriks role→izin (migration 014).

Role 'admin' = superuser (bypass, tak dicek di sini). Role lain dicek ke tabel
role_permissions (dikelola user via UI /admin/permissions). Tanpa cache: query
tabel kecil per cek (aman lintas worker gunicorn, seleksi terindeks & ringan).
"""
from .extensions import db
from .models import RolePermission

# Katalog izin: (code, label, category). Sumber kebenaran utk UI & seed.
PERMISSIONS = [
    # Laporan
    ("report.business", "Lihat Laporan Bisnis", "Laporan"),
    ("report.management", "Lihat Laporan Manajemen (owner)", "Laporan"),
    ("holding.manage", "Kelola Beban Holding/Owner", "Laporan"),
    # Master data
    ("master.view", "Lihat data & laporan penjualan", "Master Data"),
    ("venue.manage", "Kelola Venue", "Master Data"),
    ("area.manage", "Kelola Area", "Master Data"),
    ("product.manage", "Kelola Produk", "Master Data"),
    ("facility.manage", "Kelola Lapangan & Tiket", "Master Data"),
    ("promo.manage", "Kelola Promo", "Master Data"),
    ("setup.manage", "Kelola Setup Kasir (terminal & akun kasir)", "Master Data"),
    ("order.cancel", "Batalkan order/booking", "Master Data"),
    ("hr.manage", "Kelola karyawan & kasbon", "Master Data"),
    ("station.manage", "Kelola Station Gaming (arena esport)", "Master Data"),
    # Operasional
    ("ops.view", "Lihat pengajuan dana", "Operasional"),
    ("ops.create", "Buat pengajuan dana", "Operasional"),
    ("ops.approve", "Setujui & cairkan dana", "Operasional"),
    ("ops.budget", "Kelola plafon budget", "Operasional"),
    ("ops.category", "Kelola kategori beban (venue sendiri)", "Operasional"),
    # Procurement
    ("proc.view", "Lihat PO & stok", "Procurement"),
    ("proc.create", "Buat/approve/terima PO", "Procurement"),
    ("proc.supplier", "Kelola supplier", "Procurement"),
    ("proc.pay", "Bayar PO", "Procurement"),
    # Payroll
    ("payroll.view", "Lihat payroll", "Payroll"),
    ("payroll.generate", "Generate gaji", "Payroll"),
    ("payroll.approve", "Setujui & bayar gaji", "Payroll"),
    # Kas & Bank
    ("treasury.manage", "Kelola Kas & Bank", "Kas & Bank"),
]

PERMISSION_CODES = {p[0] for p in PERMISSIONS}

# Role yang izinnya bisa diatur di UI (admin = superuser, tak diedit)
EDITABLE_ROLES = [
    ("head_office", "Head Office"),
    ("manager_unit", "Manager Unit"),
    ("admin_unit", "Admin Unit (Area)"),
    ("staff", "Kasir"),
    ("staff_other", "Ass. Manager/SPV / Staff"),
]

# Default grant (dipakai saat seed ulang bila perlu; SQL migration 014 sudah seed)
DEFAULT_GRANTS = {
    "head_office": PERMISSION_CODES,
    "manager_unit": {
        "master.view", "hr.manage", "ops.view", "ops.create", "ops.budget", "ops.category",
        "proc.view", "proc.create", "payroll.view", "payroll.generate",
        "report.business", "station.manage",
    },
    "admin_unit": {"ops.view", "ops.create", "product.manage", "facility.manage", "promo.manage"},
    "staff": set(),
    "staff_other": set(),
}


def has_perm(role: str, code: str) -> bool:
    """True bila role punya izin. admin = superuser (selalu True)."""
    if role == "admin":
        return True
    return (
        db.session.query(RolePermission.id)
        .filter_by(role=role, permission_code=code)
        .first()
        is not None
    )


def perms_for_role(role: str) -> list:
    """Daftar izin (codes) yang dimiliki role — utk dikirim ke frontend. admin=semua."""
    if role == "admin":
        return sorted(PERMISSION_CODES)
    return sorted(
        rp.permission_code for rp in RolePermission.query.filter_by(role=role).all()
    )


def grants_matrix() -> dict:
    """{role: [codes]} utk semua role editable — dipakai UI."""
    out = {r: [] for r, _ in EDITABLE_ROLES}
    for rp in RolePermission.query.all():
        out.setdefault(rp.role, []).append(rp.permission_code)
    return out


def set_grant(role: str, code: str, granted: bool):
    existing = RolePermission.query.filter_by(role=role, permission_code=code).first()
    if granted and not existing:
        db.session.add(RolePermission(role=role, permission_code=code))
    elif not granted and existing:
        db.session.delete(existing)
    db.session.commit()


def seed_defaults():
    """Seed grant default hanya bila tabel kosong (dipakai CLI/first-run)."""
    if RolePermission.query.first():
        return 0
    n = 0
    for role, codes in DEFAULT_GRANTS.items():
        for c in codes:
            db.session.add(RolePermission(role=role, permission_code=c))
            n += 1
    db.session.commit()
    return n
