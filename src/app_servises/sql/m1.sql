-- migrations/sql/V10__create_data_sources_table.sql
CREATE TABLE IF NOT EXISTS app_servises.data_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    folder_path VARCHAR(255) NOT NULL,  -- имя папки относительно DATA_ROOT_DIR
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_checked TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_sources_active ON app_servises.data_sources(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_data_sources_folder ON app_servises.data_sources(folder_path);

COMMENT ON TABLE  app_servises.data_sources IS 'Реестр источников данных для автоматической проверки';
COMMENT ON COLUMN app_servises.data_sources.folder_path IS 'Имя папки в DATA_ROOT_DIR (например, API-TEST-1)';