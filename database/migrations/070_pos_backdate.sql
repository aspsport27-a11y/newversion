-- 070: mode back-date POS (latihan). Saklar global di app_settings + kolom
-- biz_date pada shift (NULL = shift normal hari ini; terisi = shift tanggal mundur).
CREATE TABLE IF NOT EXISTS app_settings (
    key         VARCHAR(60) PRIMARY KEY,
    value       TEXT,
    updated_at  TIMESTAMP DEFAULT now()
);

ALTER TABLE shifts ADD COLUMN IF NOT EXISTS biz_date DATE;

-- default: mode back-date MATI
INSERT INTO app_settings (key, value)
VALUES ('pos_backdate_enabled', 'false')
ON CONFLICT (key) DO NOTHING;
