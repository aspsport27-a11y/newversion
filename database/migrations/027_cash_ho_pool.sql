-- Kas Fisik HO: pool kas non-bank sbg titik singgah antara kas unit dan
-- rekening holding, supaya kas bisa dipakai opex sebelum benar2 disetor.

ALTER TABLE cash_deposits ADD COLUMN IF NOT EXISTS from_account_id INTEGER REFERENCES bank_accounts(id);

INSERT INTO bank_accounts (name, type, opening_balance, is_active, created_at, updated_at)
SELECT 'Kas Fisik HO', 'cash_ho', 0, true, now(), now()
WHERE NOT EXISTS (SELECT 1 FROM bank_accounts WHERE type = 'cash_ho');
