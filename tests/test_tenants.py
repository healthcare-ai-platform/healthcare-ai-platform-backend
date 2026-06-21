"""
GET /api/v1/tenants/
"""
import pytest
from unittest.mock import patch

from tests.conftest import AUTH_HEADER


def _fake_tenant_row(**overrides):
    base = {
        "id":       "11111111-0000-0000-0000-000000000001",
        "name":     "City General Health System",
        "docs":     3,
        "failures": 0,
        "avg_time": "N/A",
        "total_count": 1,
    }
    base.update(overrides)
    return base


# ── unit tests ────────────────────────────────────────────────────────────────

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
    assert tenant["id"]   == row["id"]
    assert tenant["name"] == "City General Health System"
    assert tenant["docs"] == 3
    assert tenant["failures"] == 0
    assert "initials" in tenant
    assert "color" in tenant
    assert "bg" in tenant
    assert "sla" in tenant
    assert "avgTime" in tenant


async def test_tenants_initials_computed(unit_client):
    row = _fake_tenant_row(name="City General Health System")
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/tenants/", headers=AUTH_HEADER)
    tenant = r.json()["items"][0]
    assert tenant["initials"] == "CG"


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
