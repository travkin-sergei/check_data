-- ============================================================
-- DDL СКРИПТ ДЛЯ app_auth (PostgreSQL 15)
-- Соответствует моделям из src/app_auth/models.py
-- Запуск: psql -U postgres -d postgres -f create_auth_schema.sql
-- ============================================================

-- 1. Создаём схему (если нет)
CREATE SCHEMA IF NOT EXISTS app_auth;
COMMENT ON SCHEMA app_auth IS 'Схема модуля авторизации (app_auth)';

-- 2. Функция автообновления updated_at (переиспользуемая)
CREATE OR REPLACE FUNCTION app_auth.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Таблица ролей (соответствует Role в models.py)
CREATE TABLE IF NOT EXISTS app_auth.roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Триггер на updated_at
DROP TRIGGER IF EXISTS trg_roles_updated ON app_auth.roles;
CREATE TRIGGER trg_roles_updated
    BEFORE UPDATE ON app_auth.roles
    FOR EACH ROW
    EXECUTE FUNCTION app_auth.set_updated_at();

-- 4. Таблица пользователей (соответствует User в models.py)
CREATE TABLE IF NOT EXISTS app_auth.users (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role_id INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    -- 🔹 ForeignKey ДОЛЖЕН указывать схему явно (как в models.py)
    CONSTRAINT fk_users_role
        FOREIGN KEY (role_id)
        REFERENCES app_auth.roles(id)
        ON DELETE SET DEFAULT
);

-- Индексы для ускорения поиска
CREATE INDEX IF NOT EXISTS idx_users_email ON app_auth.users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone ON app_auth.users(phone_number);
CREATE INDEX IF NOT EXISTS idx_users_role ON app_auth.users(role_id);

-- Триггер на updated_at
DROP TRIGGER IF EXISTS trg_users_updated ON app_auth.users;
CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON app_auth.users
    FOR EACH ROW
    EXECUTE FUNCTION app_auth.set_updated_at();

-- 5. Инициализация: роль "user" с id=1 (требуется для DEFAULT в users.role_id)
INSERT INTO app_auth.roles (id, name, description) VALUES
    (1, 'user', 'Обычный пользователь'),
    (3, 'moderator', 'Модератор'),
    (4, 'admin', 'Администратор')
ON CONFLICT (id) DO NOTHING;

-- 6. Комменты для документации и ORM
COMMENT ON TABLE app_auth.roles IS 'Роли для RBAC';
COMMENT ON TABLE app_auth.users IS 'Пользователи системы';
COMMENT ON COLUMN app_auth.users.role_id IS 'Ссылка на app_auth.roles (default=1: user)';

-- migrations/sql/V2__create_app_credentials_table.sql
CREATE TABLE IF NOT EXISTS app_auth.app_credentials (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_name VARCHAR(50) NOT NULL UNIQUE,
    app_description VARCHAR(200),
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER NOT NULL REFERENCES app_auth.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_credentials_app_name ON app_auth.app_credentials(app_name);

CREATE TABLE IF NOT EXISTS app_auth.app_credentials (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_name VARCHAR(50) NOT NULL UNIQUE,
    app_description VARCHAR(200),
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER NOT NULL REFERENCES app_auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- migrations/sql/V3__add_updated_at_to_app_credentials.sql
ALTER TABLE app_auth.app_credentials
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Триггер для автообновления updated_at (переиспользуем функцию из схемы)
DROP TRIGGER IF EXISTS trg_app_credentials_updated ON app_auth.app_credentials;
CREATE TRIGGER trg_app_credentials_updated
BEFORE UPDATE ON app_auth.app_credentials
FOR EACH ROW
EXECUTE FUNCTION app_auth.set_updated_at();

-- Комментарий для документации
COMMENT ON COLUMN app_auth.app_credentials.updated_at IS 'Дата последнего обновления записи';

-- Добавляем поле expires_at в таблицу app_credentials
ALTER TABLE app_auth.app_credentials
ADD COLUMN expires_at TIMESTAMPTZ DEFAULT NULL;

-- Опционально: добавляем индекс для быстрой очистки истёкших токенов
CREATE INDEX idx_app_credentials_expires_at ON app_auth.app_credentials(expires_at);