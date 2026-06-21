"""
GET /api/v1/audit/
"""
import pytest
from unittest.mock import patch

from tests.conftest import AUTH_HEADER


def _fake_log_row(**overrides):
    base = {
        "id":          "aaaaaaaa-0000-0000-0000-000000000001",
        "username":    "Dr. John Smith",
        "action":      "upload",
        "resource":    "document",
        "ip":          "192.168.1.10",
        "time":        "11:42 AM",
        "tenant":      "City General Health System",
        "total_count": 1,
    }
    base.update(overrides)
    return base


# ── unit tests ────────────────────────────────────────────────────────────────

async def test_audit_empty(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await unit_client.get("/api/v1/audit/", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_audit_log_shape(unit_client):
    row = _fake_log_row()
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/audit/", headers=AUTH_HEADER)
    body = r.json()
    assert body["total"] == 1
    log = body["items"][0]
    assert log["id"]       == row["id"]
    assert log["user"]     == "Dr. John Smith"
    assert log["action"]   == "upload"
    assert log["resource"] == "document"
    assert log["ip"]       == "192.168.1.10"
    assert log["time"]     == "11:42 AM"
    assert log["tenant"]   == "City General Health System"


async def test_audit_search_passed(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await unit_client.get("/api/v1/audit/?search=upload", headers=AUTH_HEADER)
    params = mock_fetch.call_args[0][1]
    assert params["search"] == "upload"


async def test_audit_tenant_filter_applied(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await unit_client.get("/api/v1/audit/", headers=AUTH_HEADER)
    from tests.conftest import SEED_TENANT_ID
    params = mock_fetch.call_args[0][1]
    assert params["tenant_id"] == SEED_TENANT_ID


# ── integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_integration_audit_list(client):
    r = await client.get("/api/v1/audit/", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 4, "Expected 4 seed audit log entries"
    for log in body["items"]:
        assert log["user"]
        assert log["action"]
        assert log["resource"]


@pytest.mark.integration
async def test_integration_audit_search(client):
    r = await client.get("/api/v1/audit/?search=upload", headers=AUTH_HEADER)
    assert r.status_code == 200
    for log in r.json()["items"]:
        assert "upload" in log["action"].lower() or "upload" in log["user"].lower()
