-- PostgreSQL schema for phase 1: company signup and shared login.
-- Covers:
-- 1. Company creation on first signup
-- 2. First admin user creation
-- 3. Shared login for admin, manager, and employee
-- 4. Session storage for refresh-token style authentication

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('admin', 'manager', 'employee');
    END IF;
END
$$;


CREATE SEQUENCE IF NOT EXISTS admin_login_seq START WITH 1001 INCREMENT BY 1;
CREATE SEQUENCE IF NOT EXISTS manager_login_seq START WITH 1001 INCREMENT BY 1;
CREATE SEQUENCE IF NOT EXISTS employee_login_seq START WITH 1001 INCREMENT BY 1;


CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(180) NOT NULL UNIQUE,
    country_name VARCHAR(120) NOT NULL,
    currency_code VARCHAR(10) NOT NULL,
    currency_name VARCHAR(120),
    currency_symbol VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT companies_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT companies_slug_not_blank CHECK (btrim(slug) <> ''),
    CONSTRAINT companies_country_not_blank CHECK (btrim(country_name) <> ''),
    CONSTRAINT companies_currency_code_not_blank CHECK (btrim(currency_code) <> '')
);


CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    login_id VARCHAR(30) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role user_role NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_login_id_not_blank CHECK (btrim(login_id) <> ''),
    CONSTRAINT users_name_not_blank CHECK (btrim(full_name) <> ''),
    CONSTRAINT users_email_not_blank CHECK (btrim(email) <> '')
);


ALTER TABLE users ADD COLUMN IF NOT EXISTS login_id VARCHAR(30);


CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash TEXT NOT NULL,
    user_agent TEXT,
    ip_address INET,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS login_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    email_attempted VARCHAR(255) NOT NULL,
    was_successful BOOLEAN NOT NULL,
    ip_address INET,
    user_agent TEXT,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_users_company_id ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_users_login_id ON users(login_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_login_audit_logs_user_id ON login_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_login_audit_logs_attempted_at ON login_audit_logs(attempted_at);


-- Example flow supported by this schema:
-- 1. Signup inserts into companies
-- 2. Signup inserts first admin into users with role = 'admin'
-- 3. Login checks users.email + password_hash
-- 4. Login creates auth_sessions row for refresh/session tracking


-- Example first signup transaction:
-- INSERT INTO companies (name, slug, country_name, currency_code, currency_name, currency_symbol)
-- VALUES ('Northstar Holdings', 'northstar-holdings', 'United States', 'USD', 'United States dollar', '$');
--
-- INSERT INTO users (company_id, full_name, email, password_hash, role, is_email_verified)
-- VALUES (
--     '<company_uuid>',
--     'Sarah Malik',
--     'admin@northstar.com',
--     '<hashed_password>',
--     'admin',
--     TRUE
-- );