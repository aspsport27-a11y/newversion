"""Model Operasional & Budget."""
from datetime import datetime

from ..extensions import db


class ExpenseCategory(db.Model):
    __tablename__ = "expense_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "is_active": self.is_active, "sort_order": self.sort_order}


class Budget(db.Model):
    __tablename__ = "budgets"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id", ondelete="CASCADE"), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class OpRequest(db.Model):
    __tablename__ = "op_requests"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    period_month = db.Column(db.Integer, nullable=False)
    period_year = db.Column(db.Integer, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    total_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    description = db.Column(db.Text)
    status = db.Column(db.String(12), nullable=False, default="submitted")  # submitted|approved|rejected|disbursed
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    disbursed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    disbursed_at = db.Column(db.DateTime)
    source_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("OpRequestItem", backref="request", lazy="selectin", cascade="all, delete-orphan")
    attachments = db.relationship("OpRequestAttachment", backref="request", lazy="selectin", cascade="all, delete-orphan")

    def to_dict(self, categories=None):
        f = lambda v: float(v) if v is not None else None
        return {
            "id": self.id,
            "code": self.code,
            "venue_id": self.venue_id,
            "period_month": self.period_month,
            "period_year": self.period_year,
            "total_amount": f(self.total_amount),
            "description": self.description,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "disbursed_at": self.disbursed_at.isoformat() if self.disbursed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "items": [i.to_dict(categories) for i in self.items],
            "attachments": [a.to_dict() for a in self.attachments],
        }


class OpRequestItem(db.Model):
    __tablename__ = "op_request_items"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("op_requests.id", ondelete="CASCADE"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id"), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, categories=None):
        cat_name = categories.get(self.category_id) if categories else None
        return {
            "id": self.id,
            "category_id": self.category_id,
            "category_name": cat_name,
            "amount": float(self.amount),
            "note": self.note,
        }


class OpRequestAttachment(db.Model):
    __tablename__ = "op_request_attachments"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("op_requests.id", ondelete="CASCADE"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
        }
