"""Model Financial — Beban Holding/Owner (sensitif, HO-only).

Pengeluaran level holding (prive, fee direktur, bonus) yang tidak menyentuh venue.
Hanya muncul di Laporan Manajemen. Saat dicatat, uang keluar dari rekening holding
(via treasury.record_tx) → saldo holding berkurang & tampil di buku besar.
"""
from datetime import datetime

from ..extensions import db

# Kategori beban holding yang dikenal (owner-sensitif)
HOLDING_CATEGORIES = ["Prive", "Fee Direktur", "Bonus", "Lainnya"]


class HoldingExpense(db.Model):
    __tablename__ = "holding_expenses"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    category = db.Column(db.String(40), nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    expense_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    source_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "category": self.category,
            "description": self.description,
            "amount": float(self.amount or 0),
            "expense_date": self.expense_date.isoformat() if self.expense_date else None,
            "source_account_id": self.source_account_id,
        }
