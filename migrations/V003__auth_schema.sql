-- V003: Add auth columns, expand role/status enums, create invites table, seed platform admin
-- Safe to re-run: uses IF NOT EXISTS / DO blocks for idempotency

BEGIN;

-- ── 1. Expand users.role to include new roles ─────────────────────────────────
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('admin', 'doctor', 'analyst', 'ops', 'viewer',
                    'platform_admin', 'tenant_admin', 'manager'));

-- ── 2. Expand users.status to include 'invited' ───────────────────────────────
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_check;
ALTER TABLE users ADD CONSTRAINT users_status_check
    CHECK (status IN ('active', 'inactive', 'suspended', 'invited'));

-- ── 3. Add missing auth columns to users ─────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS facility_id   UUID;
ALTER TABLE users ADD COLUMN IF NOT EXISTS invited_by    UUID;

-- ── 4. FK from users.facility_id → facilities ─────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_facility_id_fkey'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_facility_id_fkey
            FOREIGN KEY (facility_id) REFERENCES facilities (facility_id);
    END IF;
END $$;

-- ── 5. FK from users.invited_by → users ──────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_invited_by_fkey'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_invited_by_fkey
            FOREIGN KEY (invited_by) REFERENCES users (user_id);
    END IF;
END $$;

-- ── 6. invites table ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS invites (
    invite_id  UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID      NOT NULL REFERENCES users (user_id),
    tenant_id  UUID      NOT NULL REFERENCES tenants (tenant_id),
    token      VARCHAR   UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at    TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── 7. audit_logs: cast ip_address column to text for easier inserts ──────────
-- (existing column is INET; keep it, backend casts on read)

-- ── 8. Seed: platform admin user ─────────────────────────────────────────────
-- A dedicated platform-admin tenant so the user doesn't share a tenant with real data.
INSERT INTO tenants (tenant_id, name, plan, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'Platform', 'enterprise', 'active')
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO users (user_id, tenant_id, name, email, role, status)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    'Platform Admin',
    'admin@healthai.local',
    'platform_admin',
    'invited'
)
ON CONFLICT (user_id) DO UPDATE
    SET role = 'platform_admin',
        email = EXCLUDED.email;

COMMIT;
