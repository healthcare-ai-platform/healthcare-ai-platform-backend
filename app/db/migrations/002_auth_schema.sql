-- Migration 002: auth, facilities, invites
-- Run with: psql $DATABASE_URL -f app/db/migrations/002_auth_schema.sql
-- Safe to re-run: uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS throughout.

-- ── tenants: add plan/status if schema predates this migration ────────────────
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan       VARCHAR NOT NULL DEFAULT 'standard';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status     VARCHAR NOT NULL DEFAULT 'active';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

-- ── users: add auth + role columns ───────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS email         VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role          VARCHAR NOT NULL DEFAULT 'analyst';
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS status        VARCHAR NOT NULL DEFAULT 'invited';
ALTER TABLE users ADD COLUMN IF NOT EXISTS facility_id   UUID;
ALTER TABLE users ADD COLUMN IF NOT EXISTS invited_by    UUID;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at    TIMESTAMP DEFAULT NOW();

-- Unique index on email (partial — allows NULLs to coexist)
CREATE UNIQUE INDEX IF NOT EXISTS users_email_idx ON users (email) WHERE email IS NOT NULL;

-- ── facilities ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facilities (
    facility_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants (tenant_id),
    name        VARCHAR NOT NULL,
    city        VARCHAR,
    state       VARCHAR,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- FK from users.facility_id now that the table exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_facility_id_fkey'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_facility_id_fkey
            FOREIGN KEY (facility_id) REFERENCES facilities (facility_id);
    END IF;
END $$;

-- FK from users.invited_by
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_invited_by_fkey'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_invited_by_fkey
            FOREIGN KEY (invited_by) REFERENCES users (user_id);
    END IF;
END $$;

-- ── invites ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS invites (
    invite_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users (user_id),
    tenant_id  UUID NOT NULL REFERENCES tenants (tenant_id),
    token      VARCHAR UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at    TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── audit_logs: ensure ip_address column exists ───────────────────────────────
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS resource   VARCHAR;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip_address VARCHAR;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

-- ── Seed: platform admin user ─────────────────────────────────────────────────
-- Preserves the hardcoded seed user_id used by existing fixtures.
-- Password is NOT set here — run the accept-invite flow or set directly:
--   UPDATE users
--      SET status = 'active',
--          password_hash = '<bcrypt_hash>'
--    WHERE email = 'admin@healthcare-platform.com';
-- Generate hash: python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('YourPassword'))"
INSERT INTO users (user_id, tenant_id, name, email, role, status)
VALUES (
    '33333333-0000-0000-0000-000000000002',
    '11111111-0000-0000-0000-000000000001',
    'Platform Admin',
    'admin@healthcare-platform.com',
    'platform_admin',
    'invited'
)
ON CONFLICT (user_id) DO UPDATE
    SET role   = 'platform_admin',
        email  = COALESCE(users.email, EXCLUDED.email);
