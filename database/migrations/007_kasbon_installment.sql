-- ============================================
-- Migration 007 — cicilan kasbon per bulan
-- employees.kasbon_installment: nominal potongan kasbon tetap tiap gajian.
-- Payroll (modul nanti) potong MIN(kasbon_installment, saldo_kasbon) per bulan.
-- Target DB: venue_system. Idempotent.
-- ============================================
BEGIN;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS kasbon_installment DECIMAL(15,2);
COMMIT;
