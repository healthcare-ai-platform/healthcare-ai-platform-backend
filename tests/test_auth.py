"""
Auth flows:
  - Missing token          → 401 on all protected routes
  - POST /auth/login       → tokens on success, 401 on bad credentials
  - POST /auth/accept-invite → tokens on success, 400 on bad/expired/used token
  - POST /auth/refresh     → new token pair on valid refresh token
"""
import pytest
from unittest.mock import patch

from app.core.auth import create_refresh_token, decode_token, hash_password
from tests.conftest import AUTH_HEADER, SEED_TENANT_ID, SEED_USER_ID

# Pre-compute once — bcrypt is slow; computing at module load avoids per-test cost.
_VALID_PW = "Test1234!"
_VALID_PW_HASH = hash_password(_VALID_PW)


# ── Routes that require a Bearer token ───────────────────────────────────────

ALL_PROTECTED_ROUTES = [
    ("GET",  "/api/v1/patients/"),
    ("GET",  "/api/v1/tenants/"),
    ("GET",  "/api/v1/queue/"),
    ("GET",  "/api/v1/audit/"),
    # admin
    ("GET",  "/api/v1/admin/tenants"),
    ("POST", "/api/v1/admin/tenants"),
    # tenant management
    ("POST", "/api/v1/tenants/fake-id/facilities"),
    ("GET",  "/api/v1/tenants/fake-id/facilities"),
    ("POST", "/api/v1/tenants/fake-id/users/invite"),
    ("GET",  "/api/v1/tenants/fake-id/users"),
]

# Routes reachable by tenant_admin (used to confirm 401 is the only auth failure)
TENANT_ACCESSIBLE_ROUTES = [
    ("GET", "/api/v1/patients/"),
    ("GET", "/api/v1/tenants/"),
    ("GET", "/api/v1/queue/"),
    ("GET", "/api/v1/audit/"),
]


@pytest.mark.parametrize("method,path", ALL_PROTECTED_ROUTES)
async def test_missing_token_returns_401(anon_unit_client, method, path):
    r = await anon_unit_client.request(method, path)
    assert r.status_code == 401, f"{method} {path} should be 401 without token"


@pytest.mark.parametrize("method,path", TENANT_ACCESSIBLE_ROUTES)
async def test_valid_token_not_rejected(unit_client, method, path):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await unit_client.request(method, path, headers=AUTH_HEADER)
    assert r.status_code != 401, f"{method} {path} rejected a valid token with 401"


# ── POST /auth/login ─────────────────────────────────────────────────────────

async def test_login_success(unit_client):
    user_row = {
        "user_id":       SEED_USER_ID,
        "tenant_id":     SEED_TENANT_ID,
        "facility_id":   None,
        "role":          "tenant_admin",
        "password_hash": _VALID_PW_HASH,
        "status":        "active",
    }
    with (
        patch("app.db.session.db.fetch_one", return_value=user_row),
        patch("app.db.session.db.execute"),
    ):
        r = await unit_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": _VALID_PW},
        )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password(unit_client):
    user_row = {
        "user_id":       SEED_USER_ID,
        "tenant_id":     SEED_TENANT_ID,
        "facility_id":   None,
        "role":          "tenant_admin",
        "password_hash": _VALID_PW_HASH,
        "status":        "active",
    }
    with patch("app.db.session.db.fetch_one", return_value=user_row):
        r = await unit_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": "WrongPassword!"},
        )
    assert r.status_code == 401


async def test_login_user_not_found(unit_client):
    with patch("app.db.session.db.fetch_one", return_value=None):
        r = await unit_client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@test.com", "password": _VALID_PW},
        )
    assert r.status_code == 401


async def test_login_invited_status_rejected(unit_client):
    user_row = {
        "user_id":       SEED_USER_ID,
        "tenant_id":     SEED_TENANT_ID,
        "facility_id":   None,
        "role":          "tenant_admin",
        "password_hash": _VALID_PW_HASH,
        "status":        "invited",
    }
    with patch("app.db.session.db.fetch_one", return_value=user_row):
        r = await unit_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": _VALID_PW},
        )
    assert r.status_code == 401


async def test_login_suspended_status_rejected(unit_client):
    user_row = {
        "user_id":       SEED_USER_ID,
        "tenant_id":     SEED_TENANT_ID,
        "facility_id":   None,
        "role":          "tenant_admin",
        "password_hash": _VALID_PW_HASH,
        "status":        "suspended",
    }
    with patch("app.db.session.db.fetch_one", return_value=user_row):
        r = await unit_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": _VALID_PW},
        )
    assert r.status_code == 401


async def test_login_access_token_contains_correct_claims(unit_client):
    user_row = {
        "user_id":       SEED_USER_ID,
        "tenant_id":     SEED_TENANT_ID,
        "facility_id":   None,
        "role":          "tenant_admin",
        "password_hash": _VALID_PW_HASH,
        "status":        "active",
    }
    with (
        patch("app.db.session.db.fetch_one", return_value=user_row),
        patch("app.db.session.db.execute"),
    ):
        r = await unit_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": _VALID_PW},
        )
    payload = decode_token(r.json()["access_token"])
    assert payload["tenant_id"] == SEED_TENANT_ID
    assert payload["user_id"]   == SEED_USER_ID
    assert payload["role"]      == "tenant_admin"
    assert payload["type"]      == "access"


# ── POST /auth/accept-invite ──────────────────────────────────────────────────

async def test_accept_invite_success(unit_client):
    invite_row = {
        "invite_id":  "inv-001",
        "user_id":    SEED_USER_ID,
        "tenant_id":  SEED_TENANT_ID,
        "used_at":    None,
        "is_expired": False,
    }
    user_row = {
        "user_id":     SEED_USER_ID,
        "tenant_id":   SEED_TENANT_ID,
        "facility_id": None,
        "role":        "tenant_admin",
    }
    with (
        patch("app.db.session.db.fetch_one", side_effect=[invite_row, user_row]),
        patch("app.db.session.db.execute"),
    ):
        r = await unit_client.post(
            "/api/v1/auth/accept-invite",
            json={"token": "valid-token", "new_password": "NewPass1234!"},
        )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_accept_invite_invalid_token(unit_client):
    with patch("app.db.session.db.fetch_one", return_value=None):
        r = await unit_client.post(
            "/api/v1/auth/accept-invite",
            json={"token": "bad-token", "new_password": "NewPass1234!"},
        )
    assert r.status_code == 400
    assert "Invalid" in r.json()["detail"]


async def test_accept_invite_already_used(unit_client):
    invite_row = {
        "invite_id":  "inv-001",
        "user_id":    SEED_USER_ID,
        "tenant_id":  SEED_TENANT_ID,
        "used_at":    "2026-01-01T00:00:00",
        "is_expired": False,
    }
    with patch("app.db.session.db.fetch_one", return_value=invite_row):
        r = await unit_client.post(
            "/api/v1/auth/accept-invite",
            json={"token": "used-token", "new_password": "NewPass1234!"},
        )
    assert r.status_code == 400
    assert "already used" in r.json()["detail"]


async def test_accept_invite_expired(unit_client):
    invite_row = {
        "invite_id":  "inv-001",
        "user_id":    SEED_USER_ID,
        "tenant_id":  SEED_TENANT_ID,
        "used_at":    None,
        "is_expired": True,
    }
    with patch("app.db.session.db.fetch_one", return_value=invite_row):
        r = await unit_client.post(
            "/api/v1/auth/accept-invite",
            json={"token": "expired-token", "new_password": "NewPass1234!"},
        )
    assert r.status_code == 400
    assert "expired" in r.json()["detail"]


# ── POST /auth/refresh ────────────────────────────────────────────────────────

async def test_refresh_success(unit_client):
    refresh_tok = create_refresh_token({
        "user_id":   SEED_USER_ID,
        "tenant_id": SEED_TENANT_ID,
        "role":      "tenant_admin",
    })
    r = await unit_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_tok})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    payload = decode_token(body["access_token"])
    assert payload["type"]      == "access"
    assert payload["role"]      == "tenant_admin"
    assert payload["tenant_id"] == SEED_TENANT_ID


async def test_refresh_with_access_token_rejected(unit_client):
    from app.core.auth import create_access_token
    access_tok = create_access_token({
        "user_id":   SEED_USER_ID,
        "tenant_id": SEED_TENANT_ID,
        "role":      "tenant_admin",
    })
    r = await unit_client.post("/api/v1/auth/refresh", json={"refresh_token": access_tok})
    assert r.status_code == 400


async def test_refresh_with_garbage_token_rejected(unit_client):
    r = await unit_client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert r.status_code == 401
