"""
Platform-admin tenant management:
  POST /api/v1/admin/tenants
  GET  /api/v1/admin/tenants
  GET  /api/v1/admin/tenants/{id}

All endpoints require role=platform_admin.
"""
import pytest
from unittest.mock import patch

from tests.conftest import ADMIN_AUTH_HEADER, AUTH_HEADER, SEED_TENANT_ID

_CREATE_BODY = {
    "org_name":    "Acme Health",
    "plan":        "standard",
    "admin_name":  "Jane Doe",
    "admin_email": "jane@acme.com",
}


def _tenant_row(**overrides):
    base = {
        "tenant_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "name":      "Acme Health",
        "plan":      "standard",
        "status":    "active",
    }
    base.update(overrides)
    return base


def _user_row(**overrides):
    base = {"user_id": "bbbbbbbb-0000-0000-0000-000000000001"}
    base.update(overrides)
    return base


# ── role enforcement ──────────────────────────────────────────────────────────

async def test_create_tenant_forbidden_for_tenant_admin(unit_client):
    """tenant_admin must not be able to create tenants."""
    r = await unit_client.post(
        "/api/v1/admin/tenants",
        json=_CREATE_BODY,
        headers=AUTH_HEADER,
    )
    assert r.status_code == 403


async def test_list_tenants_forbidden_for_tenant_admin(unit_client):
    r = await unit_client.get("/api/v1/admin/tenants", headers=AUTH_HEADER)
    assert r.status_code == 403


# ── POST /admin/tenants ───────────────────────────────────────────────────────

async def test_create_tenant_success(admin_unit_client):
    with (
        patch("app.db.session.db.fetch_one", side_effect=[_tenant_row(), _user_row()]),
        patch("app.db.session.db.execute"),
        patch("app.api.routers.admin.send_invite_email"),
    ):
        r = await admin_unit_client.post(
            "/api/v1/admin/tenants",
            json=_CREATE_BODY,
            headers=ADMIN_AUTH_HEADER,
        )
    assert r.status_code == 201
    body = r.json()
    assert body["name"]   == "Acme Health"
    assert body["plan"]   == "standard"
    assert body["status"] == "active"
    assert "tenant_id" in body


async def test_create_tenant_sends_invite_email(admin_unit_client):
    with (
        patch("app.db.session.db.fetch_one", side_effect=[_tenant_row(), _user_row()]),
        patch("app.db.session.db.execute"),
        patch("app.api.routers.admin.send_invite_email") as mock_email,
    ):
        await admin_unit_client.post(
            "/api/v1/admin/tenants",
            json=_CREATE_BODY,
            headers=ADMIN_AUTH_HEADER,
        )
    mock_email.assert_called_once()
    call_args = mock_email.call_args[0]
    assert call_args[0] == "jane@acme.com"    # to_email
    assert call_args[1] == "Jane Doe"         # name
    assert call_args[3] == "tenant_admin"     # role


async def test_create_tenant_writes_audit_log(admin_unit_client):
    with (
        patch("app.db.session.db.fetch_one", side_effect=[_tenant_row(), _user_row()]),
        patch("app.db.session.db.execute") as mock_exec,
        patch("app.api.routers.admin.send_invite_email"),
    ):
        await admin_unit_client.post(
            "/api/v1/admin/tenants",
            json=_CREATE_BODY,
            headers=ADMIN_AUTH_HEADER,
        )
    # Two execute calls: invite INSERT + audit INSERT
    assert mock_exec.call_count == 2
    audit_call_sql = mock_exec.call_args_list[-1][0][0]
    assert "audit_logs" in audit_call_sql


# ── GET /admin/tenants ────────────────────────────────────────────────────────

async def test_list_tenants_admin_success(admin_unit_client):
    rows = [
        {"tenant_id": "id-1", "name": "Tenant A", "plan": "standard", "status": "active", "created_at": None},
        {"tenant_id": "id-2", "name": "Tenant B", "plan": "pro",      "status": "active", "created_at": None},
    ]
    with patch("app.db.session.db.fetch_all", return_value=rows):
        r = await admin_unit_client.get("/api/v1/admin/tenants", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["name"] == "Tenant A"
    assert body[1]["name"] == "Tenant B"


async def test_list_tenants_admin_empty(admin_unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await admin_unit_client.get("/api/v1/admin/tenants", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    assert r.json() == []


# ── GET /admin/tenants/{id} ───────────────────────────────────────────────────

async def test_get_tenant_success(admin_unit_client):
    row = {"tenant_id": SEED_TENANT_ID, "name": "Acme Health", "plan": "standard", "status": "active", "created_at": None}
    with patch("app.db.session.db.fetch_one", return_value=row):
        r = await admin_unit_client.get(
            f"/api/v1/admin/tenants/{SEED_TENANT_ID}",
            headers=ADMIN_AUTH_HEADER,
        )
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Health"


async def test_get_tenant_not_found(admin_unit_client):
    with patch("app.db.session.db.fetch_one", return_value=None):
        r = await admin_unit_client.get(
            "/api/v1/admin/tenants/nonexistent-id",
            headers=ADMIN_AUTH_HEADER,
        )
    assert r.status_code == 404


# ── integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_integration_list_tenants_admin(client):
    r = await client.get("/api/v1/admin/tenants", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
