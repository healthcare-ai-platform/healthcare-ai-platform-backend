"""
Tenant-scoped endpoints (all require role=tenant_admin unless noted):
  GET  /api/v1/tenants/                          — platform-admin list view
  POST /api/v1/tenants/{id}/facilities
  GET  /api/v1/tenants/{id}/facilities
  POST /api/v1/tenants/{id}/users/invite
  GET  /api/v1/tenants/{id}/users               — tenant_admin or manager
  PUT  /api/v1/tenants/{id}/users/{uid}/suspend
"""
import pytest
from unittest.mock import patch

from tests.conftest import AUTH_HEADER, SEED_TENANT_ID, SEED_USER_ID

OTHER_TENANT_ID = "22222222-0000-0000-0000-000000000002"
SEED_FACILITY_ID = "cccccccc-0000-0000-0000-000000000001"
SEED_NEW_USER_ID = "dddddddd-0000-0000-0000-000000000001"


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_tenant_row(**overrides):
    base = {
        "id":          SEED_TENANT_ID,
        "name":        "City General Health System",
        "docs":        3,
        "failures":    0,
        "avg_time":    "N/A",
        "total_count": 1,
    }
    base.update(overrides)
    return base


def _facility_row(**overrides):
    base = {
        "facility_id": SEED_FACILITY_ID,
        "name":        "Downtown Clinic",
        "city":        "New York",
        "state":       "NY",
    }
    base.update(overrides)
    return base


def _user_invite_row(**overrides):
    base = {"user_id": SEED_NEW_USER_ID}
    base.update(overrides)
    return base


# ── GET / — platform-admin tenant list ───────────────────────────────────────

async def test_tenants_list_empty(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await unit_client.get("/api/v1/tenants/", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_tenants_list_shape(unit_client):
    row = _fake_tenant_row()
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/tenants/", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    tenant = body["items"][0]
    assert tenant["id"]       == row["id"]
    assert tenant["name"]     == "City General Health System"
    assert tenant["docs"]     == 3
    assert tenant["failures"] == 0
    assert "initials" in tenant
    assert "color"    in tenant
    assert "bg"       in tenant
    assert "sla"      in tenant
    assert "avgTime"  in tenant


async def test_tenants_initials_computed(unit_client):
    row = _fake_tenant_row(name="City General Health System")
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/tenants/", headers=AUTH_HEADER)
    assert r.json()["items"][0]["initials"] == "CG"


async def test_tenants_sla_ok_when_no_failures(unit_client):
    row = _fake_tenant_row(docs=10, failures=0)
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/tenants/", headers=AUTH_HEADER)
    assert r.json()["items"][0]["sla"] == "ok"


async def test_tenants_sla_risk_above_5pct(unit_client):
    row = _fake_tenant_row(docs=100, failures=10)
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/tenants/", headers=AUTH_HEADER)
    assert r.json()["items"][0]["sla"] == "risk"


async def test_tenants_color_palette_assigned(unit_client):
    rows = [_fake_tenant_row(id=f"id-{i}", name=f"Tenant {i}", total_count=5) for i in range(5)]
    with patch("app.db.session.db.fetch_all", return_value=rows):
        r = await unit_client.get("/api/v1/tenants/", headers=AUTH_HEADER)
    colors = [t["color"] for t in r.json()["items"]]
    assert len(set(colors)) > 1, "All tenants got the same color — palette rotation broken"


# ── POST /{tenant_id}/facilities ──────────────────────────────────────────────

async def test_create_facility_success(unit_client):
    with (
        patch("app.db.session.db.fetch_one", return_value=_facility_row()),
        patch("app.db.session.db.execute"),
    ):
        r = await unit_client.post(
            f"/api/v1/tenants/{SEED_TENANT_ID}/facilities",
            json={"name": "Downtown Clinic", "city": "New York", "state": "NY"},
            headers=AUTH_HEADER,
        )
    assert r.status_code == 201
    body = r.json()
    assert body["facility_id"] == SEED_FACILITY_ID
    assert body["name"]        == "Downtown Clinic"
    assert body["city"]        == "New York"
    assert body["state"]       == "NY"


async def test_create_facility_without_optional_fields(unit_client):
    row = _facility_row(city=None, state=None)
    with (
        patch("app.db.session.db.fetch_one", return_value=row),
        patch("app.db.session.db.execute"),
    ):
        r = await unit_client.post(
            f"/api/v1/tenants/{SEED_TENANT_ID}/facilities",
            json={"name": "Main Hospital"},
            headers=AUTH_HEADER,
        )
    assert r.status_code == 201
    body = r.json()
    assert body["city"]  is None
    assert body["state"] is None


async def test_create_facility_wrong_tenant_returns_403(unit_client):
    r = await unit_client.post(
        f"/api/v1/tenants/{OTHER_TENANT_ID}/facilities",
        json={"name": "Clinic"},
        headers=AUTH_HEADER,
    )
    assert r.status_code == 403


# ── GET /{tenant_id}/facilities ───────────────────────────────────────────────

async def test_list_facilities_success(unit_client):
    rows = [
        _facility_row(facility_id="fac-1", name="Clinic A"),
        _facility_row(facility_id="fac-2", name="Clinic B"),
    ]
    with patch("app.db.session.db.fetch_all", return_value=rows):
        r = await unit_client.get(
            f"/api/v1/tenants/{SEED_TENANT_ID}/facilities",
            headers=AUTH_HEADER,
        )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["name"] == "Clinic A"
    assert body[1]["name"] == "Clinic B"


async def test_list_facilities_empty(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await unit_client.get(
            f"/api/v1/tenants/{SEED_TENANT_ID}/facilities",
            headers=AUTH_HEADER,
        )
    assert r.status_code == 200
    assert r.json() == []


async def test_list_facilities_wrong_tenant_returns_403(unit_client):
    r = await unit_client.get(
        f"/api/v1/tenants/{OTHER_TENANT_ID}/facilities",
        headers=AUTH_HEADER,
    )
    assert r.status_code == 403


# ── POST /{tenant_id}/users/invite ────────────────────────────────────────────

async def test_invite_user_success(unit_client):
    with (
        patch("app.db.session.db.fetch_one", return_value=_user_invite_row()),
        patch("app.db.session.db.execute"),
        patch("app.api.routers.tenants.send_invite_email"),
    ):
        r = await unit_client.post(
            f"/api/v1/tenants/{SEED_TENANT_ID}/users/invite",
            json={
                "name":  "Alice Smith",
                "email": "alice@acme.com",
                "role":  "doctor",
            },
            headers=AUTH_HEADER,
        )
    assert r.status_code == 201
    body = r.json()
    assert body["user_id"] == SEED_NEW_USER_ID
    assert body["role"]    == "doctor"
    assert body["status"]  == "invited"


async def test_invite_user_with_facility(unit_client):
    facility_row = {"facility_id": SEED_FACILITY_ID}
    with (
        patch("app.db.session.db.fetch_one", side_effect=[facility_row, _user_invite_row()]),
        patch("app.db.session.db.execute"),
        patch("app.api.routers.tenants.send_invite_email"),
    ):
        r = await unit_client.post(
            f"/api/v1/tenants/{SEED_TENANT_ID}/users/invite",
            json={
                "name":        "Bob Jones",
                "email":       "bob@acme.com",
                "role":        "analyst",
                "facility_id": SEED_FACILITY_ID,
            },
            headers=AUTH_HEADER,
        )
    assert r.status_code == 201


async def test_invite_user_invalid_role(unit_client):
    r = await unit_client.post(
        f"/api/v1/tenants/{SEED_TENANT_ID}/users/invite",
        json={"name": "X", "email": "x@x.com", "role": "tenant_admin"},
        headers=AUTH_HEADER,
    )
    assert r.status_code == 400
    assert "Role must be one of" in r.json()["detail"]


async def test_invite_user_invalid_role_platform_admin(unit_client):
    r = await unit_client.post(
        f"/api/v1/tenants/{SEED_TENANT_ID}/users/invite",
        json={"name": "X", "email": "x@x.com", "role": "platform_admin"},
        headers=AUTH_HEADER,
    )
    assert r.status_code == 400


async def test_invite_user_facility_not_in_tenant(unit_client):
    with patch("app.db.session.db.fetch_one", return_value=None):
        r = await unit_client.post(
            f"/api/v1/tenants/{SEED_TENANT_ID}/users/invite",
            json={
                "name":        "Y",
                "email":       "y@y.com",
                "role":        "doctor",
                "facility_id": "nonexistent-facility",
            },
            headers=AUTH_HEADER,
        )
    assert r.status_code == 400
    assert "Facility not found" in r.json()["detail"]


async def test_invite_user_wrong_tenant_returns_403(unit_client):
    r = await unit_client.post(
        f"/api/v1/tenants/{OTHER_TENANT_ID}/users/invite",
        json={"name": "Z", "email": "z@z.com", "role": "doctor"},
        headers=AUTH_HEADER,
    )
    assert r.status_code == 403


async def test_invite_user_sends_email(unit_client):
    with (
        patch("app.db.session.db.fetch_one", return_value=_user_invite_row()),
        patch("app.db.session.db.execute"),
        patch("app.api.routers.tenants.send_invite_email") as mock_email,
    ):
        await unit_client.post(
            f"/api/v1/tenants/{SEED_TENANT_ID}/users/invite",
            json={"name": "Alice", "email": "alice@acme.com", "role": "doctor"},
            headers=AUTH_HEADER,
        )
    mock_email.assert_called_once()
    assert mock_email.call_args[0][0] == "alice@acme.com"


# ── GET /{tenant_id}/users ────────────────────────────────────────────────────

async def test_list_users_success(unit_client):
    rows = [
        {
            "user_id":       SEED_USER_ID,
            "name":          "Jane Doe",
            "email":         "jane@acme.com",
            "role":          "tenant_admin",
            "status":        "active",
            "facility_name": None,
        },
    ]
    with patch("app.db.session.db.fetch_all", return_value=rows):
        r = await unit_client.get(
            f"/api/v1/tenants/{SEED_TENANT_ID}/users",
            headers=AUTH_HEADER,
        )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"]  == "Jane Doe"
    assert body[0]["role"]  == "tenant_admin"


async def test_list_users_empty(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await unit_client.get(
            f"/api/v1/tenants/{SEED_TENANT_ID}/users",
            headers=AUTH_HEADER,
        )
    assert r.status_code == 200
    assert r.json() == []


async def test_list_users_wrong_tenant_returns_403(unit_client):
    r = await unit_client.get(
        f"/api/v1/tenants/{OTHER_TENANT_ID}/users",
        headers=AUTH_HEADER,
    )
    assert r.status_code == 403


# ── PUT /{tenant_id}/users/{user_id}/suspend ─────────────────────────────────

async def test_suspend_user_success(unit_client):
    with patch("app.db.session.db.execute"):
        r = await unit_client.put(
            f"/api/v1/tenants/{SEED_TENANT_ID}/users/{SEED_NEW_USER_ID}/suspend",
            headers=AUTH_HEADER,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == SEED_NEW_USER_ID
    assert body["status"]  == "suspended"


async def test_suspend_user_wrong_tenant_returns_403(unit_client):
    r = await unit_client.put(
        f"/api/v1/tenants/{OTHER_TENANT_ID}/users/{SEED_NEW_USER_ID}/suspend",
        headers=AUTH_HEADER,
    )
    assert r.status_code == 403


# ── integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_integration_tenants_list(client):
    r = await client.get("/api/v1/tenants/", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 2, "Expected 2 seed tenants"
    for t in body["items"]:
        assert t["name"]
        assert t["initials"]
        assert t["sla"] in ("ok", "risk")


@pytest.mark.integration
async def test_integration_list_users(client):
    r = await client.get(f"/api/v1/tenants/{SEED_TENANT_ID}/users", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.integration
async def test_integration_list_facilities(client):
    r = await client.get(f"/api/v1/tenants/{SEED_TENANT_ID}/facilities", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
