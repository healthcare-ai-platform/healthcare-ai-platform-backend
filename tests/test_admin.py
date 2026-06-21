"""
Platform-admin panel endpoints (all require role=platform_admin):

Tenants:
  POST /api/v1/admin/tenants
  GET  /api/v1/admin/tenants
  GET  /api/v1/admin/tenants/{id}
  PUT  /api/v1/admin/tenants/{id}/suspend

System:
  GET  /api/v1/admin/system/health
  GET  /api/v1/admin/billing
  GET  /api/v1/admin/logs

Admin users:
  GET  /api/v1/admin/users
  POST /api/v1/admin/users/invite
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


# ── PUT /admin/tenants/{id}/suspend ──────────────────────────────────────────

async def test_suspend_tenant_success(admin_unit_client):
    with (
        patch("app.db.session.db.fetch_one", return_value={"tenant_id": SEED_TENANT_ID}),
        patch("app.db.session.db.execute"),
    ):
        r = await admin_unit_client.put(
            f"/api/v1/admin/tenants/{SEED_TENANT_ID}/suspend",
            headers=ADMIN_AUTH_HEADER,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == SEED_TENANT_ID
    assert body["status"]    == "suspended"


async def test_suspend_tenant_not_found(admin_unit_client):
    with patch("app.db.session.db.fetch_one", return_value=None):
        r = await admin_unit_client.put(
            "/api/v1/admin/tenants/nonexistent/suspend",
            headers=ADMIN_AUTH_HEADER,
        )
    assert r.status_code == 404


async def test_suspend_tenant_forbidden_for_tenant_admin(unit_client):
    r = await unit_client.put(
        f"/api/v1/admin/tenants/{SEED_TENANT_ID}/suspend",
        headers=AUTH_HEADER,
    )
    assert r.status_code == 403


# ── GET /admin/system/health ──────────────────────────────────────────────────

def _health_summary():
    return {
        "total_tenants": 3,
        "docs_today":    45,
        "failed_today":  2,
        "in_progress":   8,
    }

def _health_per_tenant():
    return [
        {"tenant_id": "id-1", "name": "Clinic A", "docs_today": 30, "failed": 1, "in_progress": 5},
        {"tenant_id": "id-2", "name": "Clinic B", "docs_today": 15, "failed": 1, "in_progress": 3},
    ]


async def test_system_health_shape(admin_unit_client):
    with (
        patch("app.db.session.db.fetch_one",  return_value=_health_summary()),
        patch("app.db.session.db.fetch_all",  side_effect=[
            [{"status": "failed", "count": 2}, {"status": "loaded", "count": 43}],
            _health_per_tenant(),
        ]),
    ):
        r = await admin_unit_client.get("/api/v1/admin/system/health", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["total_tenants"] == 3
    assert body["docs_today"]    == 45
    assert body["failed_today"]  == 2
    assert "pipeline"            in body
    assert "per_tenant"          in body
    assert len(body["per_tenant"]) == 2


async def test_system_health_pipeline_keyed_by_status(admin_unit_client):
    with (
        patch("app.db.session.db.fetch_one", return_value=_health_summary()),
        patch("app.db.session.db.fetch_all", side_effect=[
            [{"status": "failed", "count": 2}, {"status": "loaded", "count": 43}],
            _health_per_tenant(),
        ]),
    ):
        r = await admin_unit_client.get("/api/v1/admin/system/health", headers=ADMIN_AUTH_HEADER)
    pipeline = r.json()["pipeline"]
    assert pipeline["failed"] == 2
    assert pipeline["loaded"] == 43


async def test_system_health_forbidden_for_tenant_admin(unit_client):
    r = await unit_client.get("/api/v1/admin/system/health", headers=AUTH_HEADER)
    assert r.status_code == 403


# ── GET /admin/billing ────────────────────────────────────────────────────────

async def test_billing_shape(admin_unit_client):
    rows = [
        {
            "tenant_id": "id-1", "name": "Clinic A", "plan": "standard", "status": "active",
            "user_count": 5, "docs_total": 200, "docs_this_month": 45,
        },
        {
            "tenant_id": "id-2", "name": "Clinic B", "plan": "pro", "status": "active",
            "user_count": 12, "docs_total": 800, "docs_this_month": 120,
        },
    ]
    with patch("app.db.session.db.fetch_all", return_value=rows):
        r = await admin_unit_client.get("/api/v1/admin/billing", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["plan"]            == "standard"
    assert body[0]["docs_this_month"] == 45
    assert body[1]["user_count"]      == 12


async def test_billing_empty(admin_unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await admin_unit_client.get("/api/v1/admin/billing", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    assert r.json() == []


async def test_billing_forbidden_for_tenant_admin(unit_client):
    r = await unit_client.get("/api/v1/admin/billing", headers=AUTH_HEADER)
    assert r.status_code == 403


# ── GET /admin/logs ───────────────────────────────────────────────────────────

def _log_row(**overrides):
    base = {
        "id":          "log-001",
        "username":    "Jane Doe",
        "action":      "upload",
        "resource":    "document",
        "ip":          "10.0.0.1",
        "time":        "01:00 PM",
        "tenant":      "Clinic A",
        "total_count": 1,
    }
    base.update(overrides)
    return base


async def test_platform_logs_shape(admin_unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[_log_row()]):
        r = await admin_unit_client.get("/api/v1/admin/logs", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    log = body["items"][0]
    assert log["user"]   == "Jane Doe"
    assert log["action"] == "upload"
    assert log["tenant"] == "Clinic A"


async def test_platform_logs_empty(admin_unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await admin_unit_client.get("/api/v1/admin/logs", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_platform_logs_search_param_passed(admin_unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await admin_unit_client.get("/api/v1/admin/logs?search=upload", headers=ADMIN_AUTH_HEADER)
    params = mock_fetch.call_args[0][1]
    assert params["search"] == "upload"


async def test_platform_logs_tenant_filter_passed(admin_unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await admin_unit_client.get(
            f"/api/v1/admin/logs?tenant_id={SEED_TENANT_ID}",
            headers=ADMIN_AUTH_HEADER,
        )
    params = mock_fetch.call_args[0][1]
    assert params["tenant_id"] == SEED_TENANT_ID


async def test_platform_logs_no_tenant_filter_by_default(admin_unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await admin_unit_client.get("/api/v1/admin/logs", headers=ADMIN_AUTH_HEADER)
    params = mock_fetch.call_args[0][1]
    assert params["tenant_id"] is None


async def test_platform_logs_forbidden_for_tenant_admin(unit_client):
    r = await unit_client.get("/api/v1/admin/logs", headers=AUTH_HEADER)
    assert r.status_code == 403


# ── GET /admin/users ──────────────────────────────────────────────────────────

async def test_list_admin_users_shape(admin_unit_client):
    rows = [
        {"user_id": "u-1", "name": "Alice", "email": "alice@sys.com", "status": "active", "created_at": None},
        {"user_id": "u-2", "name": "Bob",   "email": "bob@sys.com",   "status": "active", "created_at": None},
    ]
    with patch("app.db.session.db.fetch_all", return_value=rows):
        r = await admin_unit_client.get("/api/v1/admin/users", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["email"] == "alice@sys.com"


async def test_list_admin_users_forbidden_for_tenant_admin(unit_client):
    r = await unit_client.get("/api/v1/admin/users", headers=AUTH_HEADER)
    assert r.status_code == 403


# ── POST /admin/users/invite ──────────────────────────────────────────────────

async def test_invite_admin_user_success(admin_unit_client):
    with (
        patch("app.db.session.db.fetch_one", return_value={"user_id": "new-admin-id"}),
        patch("app.db.session.db.execute"),
        patch("app.api.routers.admin.send_invite_email"),
    ):
        r = await admin_unit_client.post(
            "/api/v1/admin/users/invite",
            json={"name": "Carol", "email": "carol@sys.com"},
            headers=ADMIN_AUTH_HEADER,
        )
    assert r.status_code == 201
    body = r.json()
    assert body["email"]  == "carol@sys.com"
    assert body["role"]   == "platform_admin"
    assert body["status"] == "invited"


async def test_invite_admin_user_sends_email(admin_unit_client):
    with (
        patch("app.db.session.db.fetch_one", return_value={"user_id": "new-id"}),
        patch("app.db.session.db.execute"),
        patch("app.api.routers.admin.send_invite_email") as mock_email,
    ):
        await admin_unit_client.post(
            "/api/v1/admin/users/invite",
            json={"name": "Carol", "email": "carol@sys.com"},
            headers=ADMIN_AUTH_HEADER,
        )
    mock_email.assert_called_once()
    assert mock_email.call_args[0][3] == "platform_admin"


async def test_invite_admin_user_forbidden_for_tenant_admin(unit_client):
    r = await unit_client.post(
        "/api/v1/admin/users/invite",
        json={"name": "X", "email": "x@x.com"},
        headers=AUTH_HEADER,
    )
    assert r.status_code == 403


# ── integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_integration_list_tenants_admin(client):
    r = await client.get("/api/v1/admin/tenants", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.integration
async def test_integration_system_health(client):
    r = await client.get("/api/v1/admin/system/health", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert "total_tenants" in body
    assert "pipeline"      in body
    assert "per_tenant"    in body


@pytest.mark.integration
async def test_integration_billing(client):
    r = await client.get("/api/v1/admin/billing", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.integration
async def test_integration_platform_logs(client):
    r = await client.get("/api/v1/admin/logs", headers=ADMIN_AUTH_HEADER)
    assert r.status_code == 200
    assert "items" in r.json()
