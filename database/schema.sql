-- ============================================
-- VENUE MANAGEMENT SYSTEM - PostgreSQL Schema
-- ============================================
-- Created: 2026-07-10
-- Database: venue_system
-- Charset: UTF-8

-- Drop existing tables if needed (careful in production!)
-- DROP TABLE IF EXISTS audit_logs CASCADE;
-- DROP TABLE IF EXISTS approvals CASCADE;
-- etc...

-- ============================================
-- 1. ORGANIZATION & VENUES
-- ============================================

CREATE TABLE IF NOT EXISTS venues (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    address TEXT,
    city VARCHAR(50),
    phone VARCHAR(20),
    email VARCHAR(100),
    manager_id INTEGER,
    capacity INTEGER,
    facilities TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    budget_allocation DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 2. EMPLOYEE & PAYROLL
-- ============================================

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    position VARCHAR(100),
    venue_id INTEGER REFERENCES venues(id) ON DELETE SET NULL,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    salary DECIMAL(15,2),
    bank_account VARCHAR(50),
    bank_name VARCHAR(50),
    phone VARCHAR(20),
    email VARCHAR(100),
    identity_number VARCHAR(20),
    status VARCHAR(20) DEFAULT 'active',
    hire_date DATE,
    birth_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payroll (
    id SERIAL PRIMARY KEY,
    payroll_id VARCHAR(20) UNIQUE NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    base_salary DECIMAL(15,2) NOT NULL,
    allowance DECIMAL(15,2) DEFAULT 0,
    deduction DECIMAL(15,2) DEFAULT 0,
    net_salary DECIMAL(15,2),
    status VARCHAR(20) DEFAULT 'draft',
    approval_date TIMESTAMP,
    approved_by_id INTEGER REFERENCES employees(id),
    paid_date TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_id, period_month, period_year)
);

-- ============================================
-- 3. SALES & REVENUE
-- ============================================

CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    booking_id VARCHAR(20) UNIQUE NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    customer_name VARCHAR(100),
    customer_phone VARCHAR(20),
    customer_email VARCHAR(100),
    facility_type VARCHAR(100),
    facility_name VARCHAR(100),
    booking_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    duration_hours INTEGER,
    price_per_hour DECIMAL(10,2),
    total_price DECIMAL(15,2) NOT NULL,
    payment_status VARCHAR(20) DEFAULT 'pending',
    payment_method VARCHAR(50),
    amount_paid DECIMAL(15,2) DEFAULT 0,
    amount_due DECIMAL(15,2),
    notes TEXT,
    created_by_id INTEGER REFERENCES employees(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_sales (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    sales_date DATE NOT NULL,
    total_revenue DECIMAL(15,2) DEFAULT 0,
    total_transactions INTEGER DEFAULT 0,
    cash_received DECIMAL(15,2) DEFAULT 0,
    transfer_received DECIMAL(15,2) DEFAULT 0,
    card_received DECIMAL(15,2) DEFAULT 0,
    notes TEXT,
    created_by_id INTEGER REFERENCES employees(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(venue_id, sales_date)
);

-- ============================================
-- 4. OPERATIONAL & BUDGET
-- ============================================

CREATE TABLE IF NOT EXISTS operational_requests (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(20) UNIQUE NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    requested_by_id INTEGER NOT NULL REFERENCES employees(id),
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(15,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',

    -- Budget Breakdown
    utilities_amount DECIMAL(15,2) DEFAULT 0,
    maintenance_amount DECIMAL(15,2) DEFAULT 0,
    supplies_amount DECIMAL(15,2) DEFAULT 0,
    marketing_amount DECIMAL(15,2) DEFAULT 0,
    other_amount DECIMAL(15,2) DEFAULT 0,

    description TEXT,
    approved_by_id INTEGER REFERENCES employees(id),
    approved_date TIMESTAMP,
    rejection_reason TEXT,
    disbursed_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS budget_allocation (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    total_budget DECIMAL(15,2),
    utilities_budget DECIMAL(15,2),
    maintenance_budget DECIMAL(15,2),
    supplies_budget DECIMAL(15,2),
    marketing_budget DECIMAL(15,2),
    actual_spent DECIMAL(15,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(venue_id, period_month, period_year)
);

-- ============================================
-- 5. PROCUREMENT & INVENTORY
-- ============================================

CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    supplier_code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    contact_person VARCHAR(100),
    phone VARCHAR(20),
    email VARCHAR(100),
    address TEXT,
    city VARCHAR(50),
    payment_terms VARCHAR(100),
    bank_account VARCHAR(50),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS procurement_requests (
    id SERIAL PRIMARY KEY,
    po_id VARCHAR(20) UNIQUE NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    supplier_id INTEGER REFERENCES suppliers(id),
    requested_by_id INTEGER NOT NULL REFERENCES employees(id),
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_cost DECIMAL(15,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    approved_by_id INTEGER REFERENCES employees(id),
    approved_date TIMESTAMP,
    expected_delivery_date DATE,
    actual_delivery_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS procurement_items (
    id SERIAL PRIMARY KEY,
    po_id VARCHAR(20) NOT NULL REFERENCES procurement_requests(po_id) ON DELETE CASCADE,
    item_name VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    unit VARCHAR(20),
    unit_price DECIMAL(10,2) NOT NULL,
    total_price DECIMAL(15,2),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inventory (
    id SERIAL PRIMARY KEY,
    item_code VARCHAR(20) UNIQUE NOT NULL,
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    item_name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    current_stock INTEGER DEFAULT 0,
    min_stock INTEGER DEFAULT 10,
    unit VARCHAR(20),
    unit_price DECIMAL(10,2),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_transactions (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(20) UNIQUE NOT NULL,
    item_code VARCHAR(20) NOT NULL REFERENCES inventory(item_code),
    venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    reference_id VARCHAR(20),
    notes TEXT,
    created_by_id INTEGER REFERENCES employees(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 6. FINANCIAL REPORTING
-- ============================================

CREATE TABLE IF NOT EXISTS financial_reports (
    id SERIAL PRIMARY KEY,
    report_id VARCHAR(20) UNIQUE NOT NULL,
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    venue_id INTEGER REFERENCES venues(id) ON DELETE CASCADE,
    report_type VARCHAR(20),

    -- Revenue
    total_revenue DECIMAL(15,2) DEFAULT 0,
    total_transactions INTEGER DEFAULT 0,

    -- Expenses
    payroll_cost DECIMAL(15,2) DEFAULT 0,
    operational_cost DECIMAL(15,2) DEFAULT 0,
    utilities_cost DECIMAL(15,2) DEFAULT 0,
    procurement_cost DECIMAL(15,2) DEFAULT 0,
    total_expenses DECIMAL(15,2) DEFAULT 0,

    -- Summary
    gross_profit DECIMAL(15,2),
    net_profit DECIMAL(15,2),
    margin_percentage DECIMAL(5,2),

    created_by_id INTEGER REFERENCES employees(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 7. SYSTEM & AUDIT
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'staff',
    active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    table_name VARCHAR(50),
    record_id VARCHAR(50),
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS approvals (
    id SERIAL PRIMARY KEY,
    approval_id VARCHAR(20) UNIQUE NOT NULL,
    request_type VARCHAR(50) NOT NULL,
    request_id VARCHAR(20) NOT NULL,
    submitted_by_id INTEGER NOT NULL REFERENCES employees(id),
    submitted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by_id INTEGER REFERENCES employees(id),
    approved_date TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 8. INDEXES for Performance
-- ============================================

CREATE INDEX idx_bookings_venue ON bookings(venue_id);
CREATE INDEX idx_bookings_date ON bookings(booking_date);
CREATE INDEX idx_bookings_status ON bookings(payment_status);

CREATE INDEX idx_daily_sales_venue ON daily_sales(venue_id);
CREATE INDEX idx_daily_sales_date ON daily_sales(sales_date);

CREATE INDEX idx_operational_requests_venue ON operational_requests(venue_id);
CREATE INDEX idx_operational_requests_status ON operational_requests(status);

CREATE INDEX idx_payroll_employee ON payroll(employee_id);
CREATE INDEX idx_payroll_period ON payroll(period_month, period_year);
CREATE INDEX idx_payroll_status ON payroll(status);

CREATE INDEX idx_employees_venue ON employees(venue_id);
CREATE INDEX idx_employees_status ON employees(status);

CREATE INDEX idx_procurement_venue ON procurement_requests(venue_id);
CREATE INDEX idx_procurement_status ON procurement_requests(status);

CREATE INDEX idx_inventory_venue ON inventory(venue_id);
CREATE INDEX idx_inventory_code ON inventory(item_code);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);

CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_table ON audit_logs(table_name);

-- ============================================
-- 9. SAMPLE DATA (Optional)
-- ============================================

-- Insert sample venues
INSERT INTO venues (code, name, type, address, city, phone, manager_id, capacity, active)
VALUES
    ('V001', 'Lapangan Bola Premium', 'lapangan_bola', 'Jl. Olahraga 1', 'Jakarta', '021-xxxx', 1, 500, TRUE),
    ('V002', 'Mini Soccer Zona A', 'mini_soccer', 'Jl. Olahraga 2', 'Jakarta', '021-xxxx', 2, 200, TRUE),
    ('V003', 'Mini Soccer Zona B', 'mini_soccer', 'Jl. Olahraga 3', 'Jakarta', '021-xxxx', 3, 200, TRUE),
    ('V004', 'Mini Soccer Zona C', 'mini_soccer', 'Jl. Olahraga 4', 'Jakarta', '021-xxxx', 4, 200, TRUE),
    ('V005', 'Mini Soccer Zona D', 'mini_soccer', 'Jl. Olahraga 5', 'Jakarta', '021-xxxx', 5, 200, TRUE),
    ('V006', 'Mini Soccer Zona E', 'mini_soccer', 'Jl. Olahraga 6', 'Jakarta', '021-xxxx', 6, 200, TRUE),
    ('V007', 'Waterpark Premium', 'waterpark', 'Jl. Kolam 1', 'Jakarta', '021-xxxx', 7, 1000, TRUE),
    ('V008', 'Waterpark Standard', 'waterpark', 'Jl. Kolam 2', 'Jakarta', '021-xxxx', 8, 800, TRUE),
    ('V009', 'Futsal Arena A', 'futsal', 'Jl. Futsal 1', 'Jakarta', '021-xxxx', 9, 150, TRUE),
    ('V010', 'Futsal Arena B', 'futsal', 'Jl. Futsal 2', 'Jakarta', '021-xxxx', 10, 150, TRUE),
    ('V011', 'Padel Court', 'padel', 'Jl. Padel 1', 'Jakarta', '021-xxxx', 11, 100, TRUE),
    ('V012', 'Esport Zone', 'esport', 'Jl. Gaming 1', 'Jakarta', '021-xxxx', 12, 300, TRUE);
    -- Note: V013 would be another venue if you have 13

-- Insert sample departments
INSERT INTO departments (venue_id, name, budget_allocation)
VALUES
    (1, 'Sales', 50000000),
    (1, 'Maintenance', 30000000),
    (1, 'Operations', 20000000);

-- ============================================
-- 10. VIEWS (Optional)
-- ============================================

-- View: Daily Revenue Summary
CREATE OR REPLACE VIEW v_daily_revenue_summary AS
SELECT
    v.id,
    v.code,
    v.name,
    ds.sales_date,
    ds.total_revenue,
    ds.total_transactions,
    ROUND((ds.total_revenue / NULLIF(COUNT(b.id), 0))::numeric, 2) as avg_transaction
FROM venues v
LEFT JOIN daily_sales ds ON v.id = ds.venue_id
LEFT JOIN bookings b ON v.id = b.venue_id
    AND DATE(b.created_at) = ds.sales_date
GROUP BY v.id, v.code, v.name, ds.sales_date, ds.total_revenue, ds.total_transactions;

-- View: Monthly Financial Summary
CREATE OR REPLACE VIEW v_monthly_financial AS
SELECT
    v.id,
    v.code,
    v.name,
    fr.period_month,
    fr.period_year,
    fr.total_revenue,
    fr.total_expenses,
    fr.gross_profit,
    fr.margin_percentage
FROM venues v
LEFT JOIN financial_reports fr ON v.id = fr.venue_id;

-- ============================================
-- 11. DONE
-- ============================================
-- Schema is ready for development!
