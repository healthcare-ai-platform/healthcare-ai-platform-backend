-- V004: password reset tokens for the "forgot password" flow
-- Safe to re-run: uses IF NOT EXISTS for idempotency

BEGIN;

CREATE TABLE IF NOT EXISTS password_resets (
    reset_id   UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID      NOT NULL REFERENCES users (user_id),
    token      VARCHAR   UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at    TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets (token);

COMMIT;
