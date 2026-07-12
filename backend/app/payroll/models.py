"""Model Payroll (batch gaji per venue/periode)."""
from datetime import datetime

from ..extensions import db


class PayrollRun(db.Model):
    __tablename__ = "payroll_runs"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    period_month = db.Column(db.Integer, nullable=False)
    period_year = db.Column(db.Integer, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    total_net = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    notes = db.Column(db.Text)
    status = db.Column(db.String(12), nullable=False, default="draft")  # draft|submitted|approved|paid|rejected
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    paid_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("PayrollItem", backref="run", lazy="selectin", cascade="all, delete-orphan")

    def to_dict(self, with_items=False):
        f = lambda v: float(v) if v is not None else None
        d = {
            "id": self.id, "code": self.code, "venue_id": self.venue_id,
            "period_month": self.period_month, "period_year": self.period_year,
            "total_net": f(self.total_net), "notes": self.notes, "status": self.status,
            "rejection_reason": self.rejection_reason,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "employee_count": len(self.items),
        }
        if with_items:
            d["items"] = [i.to_dict() for i in self.items]
        return d


class PayrollItem(db.Model):
    __tablename__ = "payroll_items"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="SET NULL"))
    employee_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100))
    base_salary = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    allowance = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    kasbon_deduction = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    other_deduction = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    net_salary = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    bank_name = db.Column(db.String(50))
    bank_account = db.Column(db.String(50))
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        f = lambda v: float(v) if v is not None else 0.0
        return {
            "id": self.id, "employee_id": self.employee_id, "employee_name": self.employee_name,
            "position": self.position, "base_salary": f(self.base_salary), "allowance": f(self.allowance),
            "kasbon_deduction": f(self.kasbon_deduction), "other_deduction": f(self.other_deduction),
            "net_salary": f(self.net_salary), "bank_name": self.bank_name, "bank_account": self.bank_account,
            "note": self.note,
        }
