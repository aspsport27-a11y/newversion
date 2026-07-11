# Sistem Manajemen Venue Olahraga - Architecture & Design Document

**Project:** Remake ASP Sport System  
**Tech Stack:** Python (Backend) + Vue.js (Frontend) + PostgreSQL (Database)  
**Status:** 0% - Planning Phase  
**Last Updated:** 2026-07-10

---

## 1. SYSTEM OVERVIEW

### 1.1 Objectives
- Centralized management untuk 13 unit venue olahraga
- Real-time data penjualan & operasional
- Workflow approval untuk pengajuan dana & gaji
- Financial reporting & analytics
- Inventory & procurement management
- Employee management & payroll

### 1.2 Units Breakdown
```
1. Lapangan Bola (1 unit)
2. Mini Soccer (5 units)
3. Waterpark (2 units)
4. Futsal (2 units)
5. Padel (1 unit)
6. Esport (1 unit)
─────────────────────
TOTAL: 13 units
```

### 1.3 User Roles & Permissions
```
┌─────────────────────────────────────┐
│      ROLE HIERARCHY                 │
├─────────────────────────────────────┤
│ Admin / Owner                       │
│   ├─ Head Office (Finance, HR)      │
│   │   ├─ Approve pengajuan dana     │
│   │   ├─ Approve gaji               │
│   │   ├─ Lihat laporan keuangan     │
│   │   └─ Manage procurement         │
│   │                                 │
│   └─ Unit Manager (per venue)       │
│       ├─ Lihat dashboard unit       │
│       ├─ Entry penjualan            │
│       ├─ Request dana operasional   │
│       ├─ Input data karyawan        │
│       └─ Request procurement        │
│                                     │
└─────────────────────────────────────┘
   ↑          ↑          ↑
 Staff      Kasir    Manager Unit
 (Input)   (Sales)   (Approval Dulu)
```

---

## 2. DATABASE SCHEMA

### 2.1 Core Tables Structure

```sql
-- ============================================
-- 1. ORGANIZATION & VENUES
-- ============================================

-- Tabel Venue/Unit
CREATE TABLE venues (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,          -- VN001, VN002, etc.
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,                 -- 'lapangan_bola', 'mini_soccer', etc.
    address TEXT,
    phone VARCHAR(20),
    manager_id INTEGER REFERENCES employees(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Tabel Departments/Units
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER REFERENCES venues(id),
    name VARCHAR(100),                         -- "Sales", "Maintenance", etc.
    budget_allocation DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 2. EMPLOYEE & PAYROLL
-- ============================================

CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(20) UNIQUE NOT NULL,   -- EMP001, EMP002, etc.
    name VARCHAR(100) NOT NULL,
    position VARCHAR(100),
    venue_id INTEGER REFERENCES venues(id),
    department_id INTEGER REFERENCES departments(id),
    salary DECIMAL(15,2),
    bank_account VARCHAR(50),
    bank_name VARCHAR(50),
    phone VARCHAR(20),
    email VARCHAR(100),
    status VARCHAR(20),                        -- 'active', 'inactive', 'leave'
    hire_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Tabel Payroll/Gaji
CREATE TABLE payroll (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    period_month INTEGER,
    period_year INTEGER,
    base_salary DECIMAL(15,2),
    allowance DECIMAL(15,2),                   -- tunjangan
    deduction DECIMAL(15,2),                   -- potongan
    net_salary DECIMAL(15,2),
    status VARCHAR(20),                        -- 'draft', 'pending', 'approved', 'paid'
    approval_date TIMESTAMP,
    paid_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- ============================================
-- 3. SALES & REVENUE
-- ============================================

CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    booking_id VARCHAR(20) UNIQUE NOT NULL,    -- BK20260710001, etc.
    venue_id INTEGER REFERENCES venues(id),
    customer_name VARCHAR(100),
    customer_phone VARCHAR(20),
    facility_type VARCHAR(100),                -- 'main_field', 'room_1', etc.
    booking_date DATE,
    start_time TIME,
    end_time TIME,
    duration_hours INTEGER,
    price_per_hour DECIMAL(10,2),
    total_price DECIMAL(15,2),
    payment_status VARCHAR(20),                -- 'pending', 'partial', 'paid'
    payment_method VARCHAR(50),                -- 'cash', 'transfer', 'card'
    amount_paid DECIMAL(15,2),
    amount_due DECIMAL(15,2),
    notes TEXT,
    created_by_id INTEGER REFERENCES employees(id),  -- kasir/staff
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Tabel Daily Sales Summary
CREATE TABLE daily_sales (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER REFERENCES venues(id),
    sales_date DATE,
    total_revenue DECIMAL(15,2),
    total_transactions INTEGER,
    cash_received DECIMAL(15,2),
    transfer_received DECIMAL(15,2),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 4. OPERATIONAL & BUDGET
-- ============================================

CREATE TABLE operational_requests (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(20) UNIQUE NOT NULL,    -- OPR20260710001
    venue_id INTEGER REFERENCES venues(id),
    requested_by_id INTEGER REFERENCES employees(id),  -- manager unit
    request_date TIMESTAMP,
    total_amount DECIMAL(15,2),
    status VARCHAR(20),                        -- 'draft', 'submitted', 'approved', 'rejected', 'disbursed'
    
    -- Budget Breakdown
    utilities_amount DECIMAL(15,2),            -- listrik, air, gas
    maintenance_amount DECIMAL(15,2),          -- perbaikan & perawatan
    supplies_amount DECIMAL(15,2),             -- supplies & consumables
    marketing_amount DECIMAL(15,2),            -- promosi
    other_amount DECIMAL(15,2),
    
    approved_by_id INTEGER REFERENCES employees(id),  -- head office
    approved_date TIMESTAMP,
    rejection_reason TEXT,
    disbursed_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Tabel Budget Allocation per Venue
CREATE TABLE budget_allocation (
    id SERIAL PRIMARY KEY,
    venue_id INTEGER REFERENCES venues(id),
    period_month INTEGER,
    period_year INTEGER,
    total_budget DECIMAL(15,2),
    utilities_budget DECIMAL(15,2),
    maintenance_budget DECIMAL(15,2),
    supplies_budget DECIMAL(15,2),
    marketing_budget DECIMAL(15,2),
    actual_spent DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 5. PROCUREMENT & INVENTORY
-- ============================================

CREATE TABLE procurement_requests (
    id SERIAL PRIMARY KEY,
    po_id VARCHAR(20) UNIQUE NOT NULL,         -- PO20260710001
    venue_id INTEGER REFERENCES venues(id),
    requested_by_id INTEGER REFERENCES employees(id),
    request_date TIMESTAMP,
    total_cost DECIMAL(15,2),
    status VARCHAR(20),                        -- 'draft', 'submitted', 'approved', 'ordered', 'received'
    approved_by_id INTEGER REFERENCES employees(id),  -- head office
    approved_date TIMESTAMP,
    expected_delivery_date DATE,
    actual_delivery_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Tabel Procurement Items (detail PO)
CREATE TABLE procurement_items (
    id SERIAL PRIMARY KEY,
    po_id VARCHAR(20) REFERENCES procurement_requests(po_id),
    item_name VARCHAR(100),
    quantity INTEGER,
    unit VARCHAR(20),                          -- 'pcs', 'box', 'kg', etc.
    unit_price DECIMAL(10,2),
    total_price DECIMAL(15,2),
    notes TEXT
);

-- Tabel Inventory/Stok Barang
CREATE TABLE inventory (
    id SERIAL PRIMARY KEY,
    item_code VARCHAR(20) UNIQUE NOT NULL,
    venue_id INTEGER REFERENCES venues(id),
    item_name VARCHAR(100),
    category VARCHAR(50),                      -- 'equipment', 'supplies', 'utilities'
    current_stock INTEGER,
    min_stock INTEGER,
    unit VARCHAR(20),
    unit_price DECIMAL(10,2),
    last_updated TIMESTAMP DEFAULT NOW()
);

-- Tabel Stock Transactions
CREATE TABLE stock_transactions (
    id SERIAL PRIMARY KEY,
    item_code VARCHAR(20) REFERENCES inventory(item_code),
    venue_id INTEGER REFERENCES venues(id),
    type VARCHAR(20),                          -- 'in', 'out', 'adjustment'
    quantity INTEGER,
    reference_id VARCHAR(20),                  -- po_id atau booking_id
    notes TEXT,
    created_by_id INTEGER REFERENCES employees(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 6. FINANCIAL REPORTING
-- ============================================

CREATE TABLE financial_reports (
    id SERIAL PRIMARY KEY,
    period_month INTEGER,
    period_year INTEGER,
    venue_id INTEGER REFERENCES venues(id),    -- NULL = head office summary
    report_type VARCHAR(20),                   -- 'monthly', 'quarterly', 'annual'
    
    -- Revenue
    total_revenue DECIMAL(15,2),
    total_transactions INTEGER,
    
    -- Expenses
    payroll_cost DECIMAL(15,2),
    operational_cost DECIMAL(15,2),
    utilities_cost DECIMAL(15,2),
    procurement_cost DECIMAL(15,2),
    total_expenses DECIMAL(15,2),
    
    -- Summary
    gross_profit DECIMAL(15,2),
    net_profit DECIMAL(15,2),
    margin_percentage DECIMAL(5,2),
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 7. SYSTEM & AUDIT
-- ============================================

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100),
    password_hash VARCHAR(255),
    employee_id INTEGER REFERENCES employees(id),
    role VARCHAR(30),                          -- 'admin', 'head_office', 'manager', 'kasir', 'staff'
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(100),
    table_name VARCHAR(50),
    record_id INTEGER,
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(50),
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE approvals (
    id SERIAL PRIMARY KEY,
    request_type VARCHAR(50),                  -- 'operational', 'payroll', 'procurement'
    request_id VARCHAR(20),
    submitted_by_id INTEGER REFERENCES employees(id),
    submitted_date TIMESTAMP,
    approved_by_id INTEGER REFERENCES employees(id),
    approved_date TIMESTAMP,
    status VARCHAR(20),                        -- 'pending', 'approved', 'rejected'
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 3. MODULE BREAKDOWN & FEATURES

### 3.1 Module 1: Dashboard & Home
**Fitur:**
- Overview sales hari ini
- List pengajuan pending
- Budget status per unit
- Quick stats (revenue, expenses, profit)
- Role-based dashboard

**API Endpoints:**
```
GET /api/dashboard/overview
GET /api/dashboard/sales-today
GET /api/dashboard/pending-requests
GET /api/dashboard/budget-status
```

---

### 3.2 Module 2: Sales Management
**Fitur:**
- Create booking
- List bookings (per venue & all)
- Payment tracking
- Daily sales report
- Sales analytics
- Facility management

**API Endpoints:**
```
POST   /api/bookings
GET    /api/bookings
GET    /api/bookings/{id}
PUT    /api/bookings/{id}
DELETE /api/bookings/{id}
GET    /api/bookings/venue/{venue_id}
POST   /api/bookings/{id}/payment
GET    /api/daily-sales
GET    /api/daily-sales/{venue_id}/{date}
```

---

### 3.3 Module 3: Operational Requests & Budget
**Fitur:**
- Submit operational request (with budget breakdown)
- List requests (manager, head office views)
- Approval workflow
- Budget tracking
- Fund disbursement tracking

**API Endpoints:**
```
POST   /api/operational-requests
GET    /api/operational-requests
GET    /api/operational-requests/{id}
PUT    /api/operational-requests/{id}
PATCH  /api/operational-requests/{id}/approve
PATCH  /api/operational-requests/{id}/reject
GET    /api/budget-allocation/{venue_id}
GET    /api/budget-status
```

---

### 3.4 Module 4: Employee & Payroll
**Fitur:**
- Employee CRUD
- Salary management
- Payroll generation
- Payroll approval workflow
- Payment history
- Salary slips

**API Endpoints:**
```
POST   /api/employees
GET    /api/employees
GET    /api/employees/{id}
PUT    /api/employees/{id}
GET    /api/employees/venue/{venue_id}

POST   /api/payroll
GET    /api/payroll
GET    /api/payroll/{id}
PATCH  /api/payroll/{id}/approve
PATCH  /api/payroll/{id}/mark-paid
GET    /api/payroll-report/{period}
```

---

### 3.5 Module 5: Procurement & Inventory
**Fitur:**
- Create PO (Purchase Order)
- Supplier management
- PO approval workflow
- Stock tracking
- Stock in/out transactions
- Reorder alerts
- Inventory reports

**API Endpoints:**
```
POST   /api/procurement
GET    /api/procurement
GET    /api/procurement/{po_id}
PATCH  /api/procurement/{po_id}/approve
GET    /api/procurement-items/{po_id}

GET    /api/inventory
GET    /api/inventory/{venue_id}
POST   /api/inventory/{item_code}/adjustment
GET    /api/inventory/low-stock
GET    /api/stock-transactions
```

---

### 3.6 Module 6: Financial Reporting
**Fitur:**
- Monthly financial reports
- Revenue vs Expense analytics
- Profit & loss statement
- Cash flow tracking
- Budget vs Actual comparison
- Export reports (PDF, Excel)
- Financial KPIs

**API Endpoints:**
```
GET    /api/reports/financial
GET    /api/reports/financial/{venue_id}/{period}
GET    /api/reports/revenue/{period}
GET    /api/reports/expense/{period}
GET    /api/reports/profit-loss/{period}
GET    /api/reports/cash-flow/{period}
POST   /api/reports/export/{type}
```

---

### 3.7 Module 7: User & Access Management
**Fitur:**
- User CRUD
- Role management
- Permission control
- Password reset
- Audit logs
- Activity tracking

**API Endpoints:**
```
POST   /api/users
GET    /api/users
GET    /api/users/{id}
PUT    /api/users/{id}
DELETE /api/users/{id}
POST   /api/auth/login
POST   /api/auth/logout
POST   /api/auth/reset-password
GET    /api/audit-logs
```

---

## 4. FRONTEND STRUCTURE

### 4.1 Vue Component Architecture
```
src/
├── components/
│   ├── common/
│   │   ├── Navbar.vue
│   │   ├── Sidebar.vue
│   │   ├── Card.vue
│   │   └── Modal.vue
│   │
│   ├── dashboard/
│   │   ├── OverviewCards.vue
│   │   ├── SalesChart.vue
│   │   ├── BudgetStatus.vue
│   │   └── PendingRequests.vue
│   │
│   ├── sales/
│   │   ├── BookingForm.vue
│   │   ├── BookingList.vue
│   │   ├── PaymentForm.vue
│   │   └── SalesReport.vue
│   │
│   ├── operational/
│   │   ├── RequestForm.vue
│   │   ├── RequestList.vue
│   │   └── ApprovalWorkflow.vue
│   │
│   ├── employees/
│   │   ├── EmployeeForm.vue
│   │   ├── EmployeeList.vue
│   │   ├── PayrollForm.vue
│   │   └── PayrollList.vue
│   │
│   ├── procurement/
│   │   ├── POForm.vue
│   │   ├── POList.vue
│   │   ├── InventoryList.vue
│   │   └── StockTransaction.vue
│   │
│   └── reports/
│       ├── FinancialReport.vue
│       ├── RevenueChart.vue
│       ├── ExpenseBreakdown.vue
│       └── ExportReport.vue
│
├── views/
│   ├── Dashboard.vue
│   ├── Sales.vue
│   ├── Operational.vue
│   ├── Employees.vue
│   ├── Procurement.vue
│   ├── Reports.vue
│   └── Users.vue
│
├── services/
│   ├── api.js
│   ├── auth.js
│   └── utils.js
│
├── store/ (Vuex)
│   ├── modules/
│   │   ├── auth.js
│   │   ├── venues.js
│   │   ├── sales.js
│   │   ├── operational.js
│   │   ├── payroll.js
│   │   └── reports.js
│   └── index.js
│
└── router/
    └── index.js
```

---

## 5. BACKEND STRUCTURE (Python/Flask)

```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── venue.py
│   │   ├── employee.py
│   │   ├── booking.py
│   │   ├── operational.py
│   │   ├── payroll.py
│   │   ├── procurement.py
│   │   ├── inventory.py
│   │   ├── financial.py
│   │   └── user.py
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── sales.py
│   │   ├── operational.py
│   │   ├── payroll.py
│   │   ├── procurement.py
│   │   ├── inventory.py
│   │   ├── reports.py
│   │   └── users.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── sales_service.py
│   │   ├── operational_service.py
│   │   ├── payroll_service.py
│   │   ├── procurement_service.py
│   │   ├── report_service.py
│   │   └── approval_service.py
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── role_check.py
│   │   └── error_handler.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── validators.py
│       ├── decorators.py
│       └── helpers.py
│
├── migrations/
├── tests/
├── requirements.txt
└── run.py
```

---

## 6. ROLE-BASED ACCESS CONTROL (RBAC)

### 6.1 Permission Matrix

| Feature | Admin | Head Office | Manager Unit | Kasir | Staff |
|---------|-------|-------------|--------------|-------|-------|
| **Dashboard** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Sales Entry** | ✅ | ❌ | ✅ | ✅ | ✅ |
| **View All Sales** | ✅ | ✅ | Own Unit | ❌ | ❌ |
| **Request Operational** | ✅ | ❌ | ✅ | ❌ | ❌ |
| **Approve Operational** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Employee CRUD** | ✅ | ✅ | Own Unit | ❌ | ❌ |
| **Payroll Management** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Procurement** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Approve Procurement** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Inventory Management** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Financial Reports** | ✅ | ✅ | Own Unit | ❌ | ❌ |
| **User Management** | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## 7. DEVELOPMENT ROADMAP

### Phase 1: Foundation (Week 1-2)
- [x] Database schema setup
- [ ] User authentication & RBAC
- [ ] Dashboard layout
- [ ] Navigation & routing

### Phase 2: Sales Module (Week 3-4)
- [ ] Booking entry form
- [ ] Payment tracking
- [ ] Daily sales summary
- [ ] Sales list & filters

### Phase 3: Operational & Budget (Week 5-6)
- [ ] Operational request form
- [ ] Approval workflow
- [ ] Budget allocation
- [ ] Request tracking

### Phase 4: Employee & Payroll (Week 7-8)
- [ ] Employee management
- [ ] Salary configuration
- [ ] Payroll generation
- [ ] Approval workflow

### Phase 5: Procurement & Inventory (Week 9-10)
- [ ] PO creation
- [ ] Supplier management
- [ ] Stock tracking
- [ ] Reorder alerts

### Phase 6: Financial Reporting (Week 11-12)
- [ ] Report generation
- [ ] Analytics & charts
- [ ] Export functionality
- [ ] KPI dashboards

### Phase 7: Testing & Deployment (Week 13-14)
- [ ] Unit tests
- [ ] Integration tests
- [ ] UAT
- [ ] Production deployment

---

## 8. TECHNOLOGY DETAILS

### 8.1 Backend (Python)
**Framework:** Flask or FastAPI
**Libraries:**
- Flask-SQLAlchemy (ORM)
- Flask-JWT-Extended (Authentication)
- Flask-CORS (CORS handling)
- SQLAlchemy-Utils (Utilities)
- Marshmallow (Serialization)
- python-dotenv (Environment)

### 8.2 Frontend (Vue)
**Framework:** Vue 3 (Composition API)
**Libraries:**
- Vue Router (Routing)
- Pinia (State management - replace Vuex)
- Axios (HTTP client)
- Chart.js / ApexCharts (Charts)
- Tailwind CSS / Bootstrap (Styling)

### 8.3 Database (PostgreSQL)
**Version:** 12+
**Extensions:** 
- uuid-ossp
- pg_trgm

---

## 9. API AUTHENTICATION & SECURITY

### 9.1 Authentication Flow
```
1. POST /api/auth/login
   - Username + Password
   - Returns: JWT Token + Refresh Token

2. Include token in header:
   Authorization: Bearer <token>

3. Token expires: 24 hours
4. Refresh token expires: 7 days
```

### 9.2 Security Measures
- Password hashing (bcrypt)
- JWT token-based auth
- HTTPS only
- CORS whitelist
- Input validation
- Rate limiting
- SQL injection prevention
- CSRF protection

---

## 10. DEPLOYMENT ARCHITECTURE

```
┌─────────────────────────────────────────┐
│         CLIENT (Vue.js)                 │
│      Running on Port 3000               │
└─────────────────┬───────────────────────┘
                  │ HTTP/HTTPS
                  ▼
┌─────────────────────────────────────────┐
│    API Gateway / Reverse Proxy          │
│      (Nginx / Apache)                   │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│    Backend API (Python/Flask)           │
│    Running on Port 5000                 │
│  ├─ Auth Service                        │
│  ├─ Sales Service                       │
│  ├─ Operational Service                 │
│  ├─ Payroll Service                     │
│  ├─ Procurement Service                 │
│  └─ Report Service                      │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│    PostgreSQL Database                  │
│    (Running on Port 5432)               │
└─────────────────────────────────────────┘
```

---

## 11. NEXT STEPS

1. ✅ Database schema finalized
2. ⏳ Setup PostgreSQL & migrations
3. ⏳ Create Flask backend structure
4. ⏳ Implement authentication
5. ⏳ Build Vue frontend layout
6. ⏳ Develop sales module first
7. ⏳ Continue with other modules

**Ready to start coding?**
