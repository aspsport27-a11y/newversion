"""Model Kas & Bank (Treasury)."""
from datetime import datetime

from ..extensions import db


class BankAccount(db.Model):
    __tablename__ = "bank_accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(10), nullable=False, default="venue")  # venue|holding
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"))
    bank_name = db.Column(db.String(50))
    account_number = db.Column(db.String(50))
    opening_balance = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, balance=None):
        return {
            "id": self.id, "name": self.name, "type": self.type, "venue_id": self.venue_id,
            "bank_name": self.bank_name, "account_number": self.account_number,
            "opening_balance": float(self.opening_balance or 0),
            "balance": balance, "is_active": self.is_active,
        }


class AccountTransaction(db.Model):
    __tablename__ = "account_transactions"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)
    direction = db.Column(db.String(3), nullable=False)  # in|out
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    ref_type = db.Column(db.String(20))
    ref_id = db.Column(db.Integer)
    tx_date = db.Column(db.Date, default=datetime.utcnow)
    note = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "direction": self.direction, "amount": float(self.amount),
            "kind": self.kind, "ref_type": self.ref_type, "ref_id": self.ref_id,
            "tx_date": self.tx_date.isoformat() if self.tx_date else None,
            "note": self.note,
        }


class CashDeposit(db.Model):
    __tablename__ = "cash_deposits"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    deposit_date = db.Column(db.Date, default=datetime.utcnow)
    to_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id"), nullable=False)
    expected_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    counted_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    variance = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    note = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        f = lambda v: float(v) if v is not None else 0.0
        return {
            "id": self.id, "code": self.code,
            "deposit_date": self.deposit_date.isoformat() if self.deposit_date else None,
            "expected_amount": f(self.expected_amount), "counted_amount": f(self.counted_amount),
            "variance": f(self.variance), "note": self.note,
        }


class QrisSettlement(db.Model):
    __tablename__ = "qris_settlements"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id"))
    from_date = db.Column(db.Date, nullable=False)
    to_date = db.Column(db.Date, nullable=False)
    system_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    actual_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    status = db.Column(db.String(10), nullable=False, default="draft")  # draft|approved
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        f = lambda v: float(v) if v is not None else 0.0
        return {
            "id": self.id, "venue_id": self.venue_id,
            "from_date": self.from_date.isoformat() if self.from_date else None,
            "to_date": self.to_date.isoformat() if self.to_date else None,
            "system_amount": f(self.system_amount), "actual_amount": f(self.actual_amount),
            "variance": round(f(self.actual_amount) - f(self.system_amount), 2),
            "status": self.status,
        }


class BankReconciliation(db.Model):
    """Rekonsiliasi bank — bandingkan saldo sistem vs rekening koran per tanggal.
    ADMIN ONLY (bukan RBAC configurable)."""
    __tablename__ = "bank_reconciliations"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)
    period_to = db.Column(db.Date, nullable=False)
    statement_balance = db.Column(db.Numeric(15, 2), nullable=False)
    system_balance = db.Column(db.Numeric(15, 2), nullable=False)
    difference = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    note = db.Column(db.Text)
    status = db.Column(db.String(10), nullable=False, default="open")  # open|resolved
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    resolved_at = db.Column(db.DateTime)

    def to_dict(self):
        f = lambda v: float(v) if v is not None else 0.0
        return {
            "id": self.id, "account_id": self.account_id,
            "period_to": self.period_to.isoformat() if self.period_to else None,
            "statement_balance": f(self.statement_balance), "system_balance": f(self.system_balance),
            "difference": f(self.difference), "note": self.note, "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
