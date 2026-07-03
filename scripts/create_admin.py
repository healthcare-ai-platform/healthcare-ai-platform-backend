"""
Create a platform_admin user directly against the database.

Deliberately a CLI script, not an HTTP endpoint — creating a platform admin
requires shell/infra access to the backend (SSH, `docker exec`, etc.), the
same trust boundary as the database credentials themselves. There is no
network-reachable route for this, so it can't be left accidentally exposed.

The password is only ever read via getpass — it is never accepted as a CLI
argument, so it can't leak into shell history or a process listing.

Usage (from healthcare-ai-platform-backend/):
    python -m scripts.create_admin --email admin@yourorg.com --name "Jane Doe"
"""

import argparse
import asyncio
import getpass
import sys
from tabnanny import check

from app.core.auth import hash_password
from app.db.session import db

PLATFORM_TENANT_ID = "00000000-0000-0000-0000-000000000001"
PLATFORM_TENANT_NAME = "Platform"

MIN_PASSWORD_LENGTH = 12


async def _ensure_platform_tenant() -> None:
    await db.execute(
        """
        INSERT INTO tenants (tenant_id, name, plan, status)
        VALUES (:tenant_id, :name, 'enterprise', 'active')
        ON CONFLICT (tenant_id) DO NOTHING
        """,
        {"tenant_id": PLATFORM_TENANT_ID, "name": PLATFORM_TENANT_NAME},
    )


async def create_admin(email: str, name: str, password: str) -> None:
    await db.connect()
    
    try:
        existing = await db.fetch_one(
            "SELECT user_id FROM users WHERE email = :email", {"email": email}
        )
        if existing:
            print(
                f"A user with email '{email}' already exists (user_id={existing['user_id']}). "
                "Aborting — use the /api/v1/admin/users/invite flow to promote an existing "
                "user, or pick a different email.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        await _ensure_platform_tenant()

        pw_hash = hash_password(password)
        row = await db.fetch_one(
            """
            INSERT INTO users (tenant_id, name, email, role, status, password_hash)
            VALUES (:tenant_id, :name, :email, 'platform_admin', 'active', :password_hash)
            RETURNING user_id::text AS user_id
            """,
            {
                "tenant_id": PLATFORM_TENANT_ID,
                "name": name,
                "email": email,
                "password_hash": pw_hash,
            },
        )
        print(f"Created platform_admin '{email}' (user_id={row['user_id']}).")
    finally:
        await db.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a platform_admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        raise SystemExit(1)

    asyncio.run(create_admin(args.email, args.name, password))


if __name__ == "__main__":
    main()
