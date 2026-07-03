# Healthcare AI Platform Backend

A minimal FastAPI backend scaffold for the Healthcare AI Platform.

## Setup

1. Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -e .
```

3. Start the development server:

```bash
python -m uvicorn app.main:create_app --reload
```

## Available endpoints

- `GET /health` - health check
- `GET /patients` - sample patient list

## Creating an admin user

There is no HTTP route to create a `platform_admin` — deliberately. An endpoint that can mint
admin accounts is a standing attack surface (the classic "bootstrap endpoint left reachable in
prod" bug class); creating the first admin should require the same trust level as the database
credentials themselves, not just network access to the API.

### 1. Production / first admin — CLI script

`scripts/create_admin.py` inserts a `platform_admin` directly via the DB connection the backend
already uses (`DATABASE_URL`). Run it from a shell that has infra access (SSH into the host,
`docker exec` into the backend container, etc.):

```bash
python -m scripts.create_admin --email admin@yourorg.com --name "Jane Doe"
```

It prompts for the password interactively (`getpass`, twice, minimum 12 characters) — the
password is never a CLI argument, so it never lands in shell history, a log line, or a process
listing. It refuses to run if the email is already in use (promote via the invite flow below
instead), and creates a dedicated `Platform` tenant for the account if one doesn't exist yet.

### 2. Invite another admin (an admin already exists)

Once logged in as an existing `platform_admin`, prefer the invite flow over the CLI script for
every admin after the first — it's audited (`audit_logs`) and doesn't require infra access:

1. `POST /api/v1/admin/users/invite` with `{"name": "...", "email": "..."}`, authenticated as the existing admin ([admin.py:334-385](app/api/routers/admin.py#L334-L385)).
   This creates the user row with `status='invited'`, generates a token in `invites`, and emails an invite link (via `send_invite_email` — check Mailhog at http://localhost:8025 in local dev).
2. The invited user opens the link (`/accept-invite?token=...` in the frontend) and sets a password via `POST /api/v1/auth/accept-invite` with `{"token": "...", "new_password": "..."}` ([auth.py:71-114](app/api/routers/auth.py#L71-L114)). This flips their status to `active` and returns a session token — no separate login step needed.

Invite tokens expire after `INVITE_EXPIRE_HOURS` (see `admin.py`); an expired or already-used token is rejected.

### 3. Local dev only — seeded credentials

Migration `V003__auth_schema.sql` seeds a `platform_admin` for convenience so you don't need to
run the CLI script just to click around locally:

```
email:    admin@healthai.local
password: Admin1234!
```

There's also a `tenant_admin` seeded per demo tenant in `V002__seed_data.sql` (e.g.
`admin@citygeneral.com`, password `Admin123!`). **Never run these seed migrations against a
production database** — the password hash is public (it's in this repo). Use the CLI script
instead for any real environment.
