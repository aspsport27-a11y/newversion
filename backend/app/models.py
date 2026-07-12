"""Model SQLAlchemy — memetakan tabel yang sudah dibuat oleh database_schema.sql.

Catatan: tabel SUDAH ada di database (dibuat via SQL), jadi model ini hanya
memetakannya untuk ORM. Jangan jalankan create_all()/migrate untuk membuat ulang.
"""
from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB

from .extensions import db
from .security import hash_password, verify_password


# ============================================================
# 1. ORGANIZATION & VENUES
# ============================================================
class Venue(db.Model):
    __tablename__ = "venues"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    address = db.Column(db.Text)
    city = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    manager_id = db.Column(db.Integer)
    capacity = db.Column(db.Integer)
    facilities = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

    departments = db.relationship("Department", backref="venue", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "type": self.type,
            "address": self.address,
            "city": self.city,
            "phone": self.phone,
            "email": self.email,
            "capacity": self.capacity,
            "active": self.active,
        }


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    budget_allocation = db.Column(db.Numeric(15, 2))
    created_at = db.Column(db.DateTime)


# ============================================================
# 2. EMPLOYEE & PAYROLL
# ============================================================
class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100))
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="SET NULL"))
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL")
    )
    salary = db.Column(db.Numeric(15, 2))
    bank_account = db.Column(db.String(50))
    bank_name = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    identity_number = db.Column(db.String(20))
    status = db.Column(db.String(20), default="active")
    hire_date = db.Column(db.Date)
    birth_date = db.Column(db.Date)
    kasbon_installment = db.Column(db.Numeric(15, 2))  # cicilan kasbon/bulan
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "name": self.name,
            "position": self.position,
            "venue_id": self.venue_id,
            "salary": float(self.salary) if self.salary is not None else None,
            "kasbon_installment": float(self.kasbon_installment) if self.kasbon_installment is not None else None,
            "bank_account": self.bank_account,
            "bank_name": self.bank_name,
            "phone": self.phone,
            "email": self.email,
            "identity_number": self.identity_number,
            "status": self.status,
            "hire_date": self.hire_date.isoformat() if self.hire_date else None,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
        }


class EmployeeDebt(db.Model):
    """Kasbon/piutang karyawan. advance = kasbon keluar, repayment = potong/bayar."""

    __tablename__ = "employee_debts"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    type = db.Column(db.String(10), nullable=False)  # advance | repayment
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    note = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "amount": float(self.amount),
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Payroll(db.Model):
    __tablename__ = "payroll"

    id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(db.String(20), unique=True, nullable=False)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    period_month = db.Column(db.Integer, nullable=False)
    period_year = db.Column(db.Integer, nullable=False)
    base_salary = db.Column(db.Numeric(15, 2), nullable=False)
    allowance = db.Column(db.Numeric(15, 2), default=0)
    deduction = db.Column(db.Numeric(15, 2), default=0)
    net_salary = db.Column(db.Numeric(15, 2))
    status = db.Column(db.String(20), default="draft")
    approval_date = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    paid_date = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)


# ============================================================
# 3. SALES & REVENUE
# ============================================================
class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(20), unique=True, nullable=False)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(100))
    facility_type = db.Column(db.String(100))
    facility_name = db.Column(db.String(100))
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    duration_hours = db.Column(db.Integer)
    price_per_hour = db.Column(db.Numeric(10, 2))
    total_price = db.Column(db.Numeric(15, 2), nullable=False)
    payment_status = db.Column(db.String(20), default="pending")
    payment_method = db.Column(db.String(50))
    amount_paid = db.Column(db.Numeric(15, 2), default=0)
    amount_due = db.Column(db.Numeric(15, 2))
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)


class DailySales(db.Model):
    __tablename__ = "daily_sales"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    sales_date = db.Column(db.Date, nullable=False)
    total_revenue = db.Column(db.Numeric(15, 2), default=0)
    total_transactions = db.Column(db.Integer, default=0)
    cash_received = db.Column(db.Numeric(15, 2), default=0)
    transfer_received = db.Column(db.Numeric(15, 2), default=0)
    card_received = db.Column(db.Numeric(15, 2), default=0)
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    created_at = db.Column(db.DateTime)


# ============================================================
# 4. OPERATIONAL & BUDGET
# ============================================================
class OperationalRequest(db.Model):
    __tablename__ = "operational_requests"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(20), unique=True, nullable=False)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_id = db.Column(
        db.Integer, db.ForeignKey("employees.id"), nullable=False
    )
    request_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Numeric(15, 2), nullable=False)
    status = db.Column(db.String(20), default="draft")
    utilities_amount = db.Column(db.Numeric(15, 2), default=0)
    maintenance_amount = db.Column(db.Numeric(15, 2), default=0)
    supplies_amount = db.Column(db.Numeric(15, 2), default=0)
    marketing_amount = db.Column(db.Numeric(15, 2), default=0)
    other_amount = db.Column(db.Numeric(15, 2), default=0)
    description = db.Column(db.Text)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    approved_date = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    disbursed_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)


class BudgetAllocation(db.Model):
    __tablename__ = "budget_allocation"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    period_month = db.Column(db.Integer, nullable=False)
    period_year = db.Column(db.Integer, nullable=False)
    total_budget = db.Column(db.Numeric(15, 2))
    utilities_budget = db.Column(db.Numeric(15, 2))
    maintenance_budget = db.Column(db.Numeric(15, 2))
    supplies_budget = db.Column(db.Numeric(15, 2))
    marketing_budget = db.Column(db.Numeric(15, 2))
    actual_spent = db.Column(db.Numeric(15, 2), default=0)
    created_at = db.Column(db.DateTime)


# ============================================================
# 5. PROCUREMENT & INVENTORY
# ============================================================
class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    supplier_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    city = db.Column(db.String(50))
    payment_terms = db.Column(db.String(100))
    bank_account = db.Column(db.String(50))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "supplier_code": self.supplier_code,
            "name": self.name,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "city": self.city,
            "payment_terms": self.payment_terms,
            "bank_account": self.bank_account,
            "active": self.active,
        }


class ProcurementRequest(db.Model):
    __tablename__ = "procurement_requests"

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.String(20), unique=True, nullable=False)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    requested_by_id = db.Column(
        db.Integer, db.ForeignKey("employees.id"), nullable=False
    )
    request_date = db.Column(db.DateTime)
    total_cost = db.Column(db.Numeric(15, 2), nullable=False)
    status = db.Column(db.String(20), default="draft")
    approved_by_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    approved_date = db.Column(db.DateTime)
    expected_delivery_date = db.Column(db.Date)
    actual_delivery_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)


class ProcurementItem(db.Model):
    __tablename__ = "procurement_items"

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(
        db.String(20),
        db.ForeignKey("procurement_requests.po_id", ondelete="CASCADE"),
        nullable=False,
    )
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20))
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_price = db.Column(db.Numeric(15, 2))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime)


class Inventory(db.Model):
    __tablename__ = "inventory"

    id = db.Column(db.Integer, primary_key=True)
    item_code = db.Column(db.String(20), unique=True, nullable=False)
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    item_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    current_stock = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=10)
    unit = db.Column(db.String(20))
    unit_price = db.Column(db.Numeric(10, 2))
    last_updated = db.Column(db.DateTime)


class StockTransaction(db.Model):
    __tablename__ = "stock_transactions"

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(20), unique=True, nullable=False)
    item_code = db.Column(
        db.String(20), db.ForeignKey("inventory.item_code"), nullable=False
    )
    venue_id = db.Column(
        db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reference_id = db.Column(db.String(20))
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    created_at = db.Column(db.DateTime)


# ============================================================
# 6. FINANCIAL REPORTING
# ============================================================
class FinancialReport(db.Model):
    __tablename__ = "financial_reports"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.String(20), unique=True, nullable=False)
    period_month = db.Column(db.Integer, nullable=False)
    period_year = db.Column(db.Integer, nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id", ondelete="CASCADE"))
    report_type = db.Column(db.String(20))
    total_revenue = db.Column(db.Numeric(15, 2), default=0)
    total_transactions = db.Column(db.Integer, default=0)
    payroll_cost = db.Column(db.Numeric(15, 2), default=0)
    operational_cost = db.Column(db.Numeric(15, 2), default=0)
    utilities_cost = db.Column(db.Numeric(15, 2), default=0)
    procurement_cost = db.Column(db.Numeric(15, 2), default=0)
    total_expenses = db.Column(db.Numeric(15, 2), default=0)
    gross_profit = db.Column(db.Numeric(15, 2))
    net_profit = db.Column(db.Numeric(15, 2))
    margin_percentage = db.Column(db.Numeric(5, 2))
    created_by_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    created_at = db.Column(db.DateTime)


# ============================================================
# 7. SYSTEM & AUDIT
# ============================================================
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employees.id", ondelete="SET NULL")
    )
    role = db.Column(db.String(30), nullable=False, default="staff")
    active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
    # POS (migration 002)
    pin_hash = db.Column(db.String(255))
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"))

    # --- password helpers ---
    def set_password(self, password: str) -> None:
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        return verify_password(password, self.password_hash)

    def touch_login(self) -> None:
        self.last_login = datetime.utcnow()

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "active": self.active,
            "employee_id": self.employee_id,
            "venue_id": self.venue_id,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(100), nullable=False)
    table_name = db.Column(db.String(50))
    record_id = db.Column(db.String(50))
    old_values = db.Column(JSONB)
    new_values = db.Column(JSONB)
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime)


class Approval(db.Model):
    __tablename__ = "approvals"

    id = db.Column(db.Integer, primary_key=True)
    approval_id = db.Column(db.String(20), unique=True, nullable=False)
    request_type = db.Column(db.String(50), nullable=False)
    request_id = db.Column(db.String(20), nullable=False)
    submitted_by_id = db.Column(
        db.Integer, db.ForeignKey("employees.id"), nullable=False
    )
    submitted_date = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    approved_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="pending")
    rejection_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
