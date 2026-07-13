"""Model Procurement (Purchase Order)."""
from datetime import datetime

from ..extensions import db


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    total_amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    notes = db.Column(db.Text)
    status = db.Column(db.String(12), nullable=False, default="submitted")  # submitted|approved|received|paid|rejected
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    received_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    received_at = db.Column(db.DateTime)
    paid_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    paid_at = db.Column(db.DateTime)
    source_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("PurchaseOrderItem", backref="po", lazy="selectin", cascade="all, delete-orphan")
    attachments = db.relationship("PoAttachment", backref="po", lazy="selectin", cascade="all, delete-orphan")

    def to_dict(self, supplier_name=None):
        f = lambda v: float(v) if v is not None else None
        return {
            "id": self.id,
            "code": self.code,
            "venue_id": self.venue_id,
            "supplier_id": self.supplier_id,
            "supplier_name": supplier_name,
            "total_amount": f(self.total_amount),
            "notes": self.notes,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "items": [i.to_dict() for i in self.items],
            "attachments": [a.to_dict() for a in self.attachments],
        }


class PurchaseOrderItem(db.Model):
    __tablename__ = "purchase_order_items"

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    item_name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20))
    unit_price = db.Column(db.Numeric(15, 2), nullable=False)
    total_price = db.Column(db.Numeric(15, 2), nullable=False)
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": float(self.unit_price),
            "total_price": float(self.total_price),
            "note": self.note,
            "is_stock": self.product_id is not None,
        }


class PoAttachment(db.Model):
    __tablename__ = "po_attachments"

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "filename": self.filename, "content_type": self.content_type, "size_bytes": self.size_bytes}
