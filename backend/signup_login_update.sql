-- Update script to migrate the original signup/login schema
-- to the newer login_id-based auth model.
--
-- This script is safe to run on an existing database that already has:
-- 1. companies
-- 2. users
-- 3. auth_sessions
-- 4. login_audit_logs
--
-- What it adds:
-- 1. login_id column on users
-- 2. role-based login ID sequences
-- 3. backfilled login IDs for existing rows
-- 4. unique index on login_id
-- 5. optional check constraint for non-blank login_id


BEGIN;


CREATE SEQUENCE IF NOT EXISTS admin_login_seq START WITH 1001 INCREMENT BY 1;
CREATE SEQUENCE IF NOT EXISTS manager_login_seq START WITH 1001 INCREMENT BY 1;
CREATE SEQUENCE IF NOT EXISTS employee_login_seq START WITH 1001 INCREMENT BY 1;


ALTER TABLE users ADD COLUMN IF NOT EXISTS login_id VARCHAR(30);


-- Backfill admin login IDs: A1001, A1002, ...
UPDATE users
SET login_id = 'A' || LPAD(nextval('admin_login_seq')::text, 4, '0')
WHERE role = 'admin'
  AND (login_id IS NULL OR btrim(login_id) = '');


-- Backfill manager login IDs: MAN1001, MAN1002, ...
UPDATE users
SET login_id = 'MAN' || LPAD(nextval('manager_login_seq')::text, 4, '0')
WHERE role = 'manager'
  AND (login_id IS NULL OR btrim(login_id) = '');


-- Backfill employee login IDs: E1001, E1002, ...
UPDATE users
SET login_id = 'E' || LPAD(nextval('employee_login_seq')::text, 4, '0')
WHERE role = 'employee'
  AND (login_id IS NULL OR btrim(login_id) = '');


-- Align sequence values with existing login IDs so future inserts continue correctly.
SELECT setval(
    'admin_login_seq',
    GREATEST(
        COALESCE((SELECT MAX(SUBSTRING(login_id FROM 2)::BIGINT) FROM users WHERE login_id ~ '^A[0-9]+$'), 1000),
        1000
    ),
    TRUE
);

SELECT setval(
    'manager_login_seq',
    GREATEST(
        COALESCE((SELECT MAX(SUBSTRING(login_id FROM 4)::BIGINT) FROM users WHERE login_id ~ '^MAN[0-9]+$'), 1000),
        1000
    ),
    TRUE
);

SELECT setval(
    'employee_login_seq',
    GREATEST(
        COALESCE((SELECT MAX(SUBSTRING(login_id FROM 2)::BIGINT) FROM users WHERE login_id ~ '^E[0-9]+$'), 1000),
        1000
    ),
    TRUE
);


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_login_id_not_blank'
    ) THEN
        ALTER TABLE users
        ADD CONSTRAINT users_login_id_not_blank CHECK (btrim(login_id) <> '');
    END IF;
END
$$;


CREATE UNIQUE INDEX IF NOT EXISTS idx_users_login_id ON users(login_id);


DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'login_id'
          AND is_nullable = 'YES'
    )
    AND NOT EXISTS (
        SELECT 1 FROM users WHERE login_id IS NULL OR btrim(login_id) = ''
    ) THEN
        ALTER TABLE users ALTER COLUMN login_id SET NOT NULL;
    END IF;
END
$$;


COMMIT;


-- After running this script:
-- admin users can login with A1001, A1002, ...
-- manager users can login with MAN1001, MAN1002, ...
-- employee users can login with E1001, E1002, ...