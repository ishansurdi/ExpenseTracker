-- PostgreSQL schema additions for admin dashboard features.
-- Safe to run multiple times.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS manager_id UUID REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS is_leadership BOOLEAN NOT NULL DEFAULT FALSE;

CREATE SEQUENCE IF NOT EXISTS manager_m_login_seq START WITH 1001 INCREMENT BY 1;

CREATE INDEX IF NOT EXISTS idx_users_manager_id ON users(manager_id);
CREATE INDEX IF NOT EXISTS idx_users_is_leadership ON users(is_leadership);

UPDATE users u
SET is_leadership = TRUE
FROM company_leadership cl
WHERE u.id = cl.finance_head_user_id OR u.id = cl.cfo_user_id;

CREATE TABLE IF NOT EXISTS company_leadership (
    company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    finance_head_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    cfo_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_leadership_users_different
        CHECK (
            finance_head_user_id IS NULL
            OR cfo_user_id IS NULL
            OR finance_head_user_id <> cfo_user_id
        )
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'expense_status') THEN
        CREATE TYPE expense_status AS ENUM (
            'submitted',
            'manager_approved',
            'finance_approved',
            'cfo_approved',
            'rejected',
            'overridden'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'approval_decision') THEN
        CREATE TYPE approval_decision AS ENUM ('approved', 'rejected');
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'override_action') THEN
        CREATE TYPE override_action AS ENUM ('force_approve', 'force_reject');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS expenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    employee_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    title VARCHAR(160) NOT NULL,
    description TEXT,
    expense_date DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    currency_code VARCHAR(10) NOT NULL,
    status expense_status NOT NULL DEFAULT 'submitted',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_expenses_company_id ON expenses(company_id);
CREATE INDEX IF NOT EXISTS idx_expenses_employee_user_id ON expenses(employee_user_id);
CREATE INDEX IF NOT EXISTS idx_expenses_status ON expenses(status);
CREATE INDEX IF NOT EXISTS idx_expenses_submitted_at ON expenses(submitted_at);

CREATE TABLE IF NOT EXISTS expense_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    expense_id UUID NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    approver_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    stage SMALLINT NOT NULL CHECK (stage IN (1,2,3)),
    decision approval_decision NOT NULL,
    comment TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_expense_stage UNIQUE (expense_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_expense_approvals_expense_id ON expense_approvals(expense_id);
CREATE INDEX IF NOT EXISTS idx_expense_approvals_approver_user_id ON expense_approvals(approver_user_id);
CREATE INDEX IF NOT EXISTS idx_expense_approvals_company_id ON expense_approvals(company_id);

CREATE TABLE IF NOT EXISTS expense_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    expense_id UUID NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    admin_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    action override_action NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_expense_overrides_expense_id ON expense_overrides(expense_id);
CREATE INDEX IF NOT EXISTS idx_expense_overrides_company_id ON expense_overrides(company_id);
