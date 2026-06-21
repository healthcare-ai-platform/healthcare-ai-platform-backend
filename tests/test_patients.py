"""
GET /api/v1/patients/

Unit tests mock db.fetch_all.
Integration tests (marked) hit real postgres with seed data.
"""
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import AUTH_HEADER, SEED_TENANT_ID

# ── helpers ──────────────────────────────────────────────────────────────────

def _fake_patient_row(**overrides):
    base = {
        "id":          "44444444-0000-0000-0000-000000000001",
        "name":        "James Wilson",
        "age":         49,
        "doctor":      "Dr. John Smith",
        "hospital":    "City General Hospital",
        "last_report": "CBC",
        "date":        "Jun 01",
        "status":      "abnormal",
        "reports":     1,
        "total_count": 1,
    }
    base.update(overrides)
    return base


# ── unit tests ────────────────────────────────────────────────────────────────

async def test_patients_list_empty(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await unit_client.get("/api/v1/patients/", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["pages"] == 0


async def test_patients_list_shape(unit_client):
    row = _fake_patient_row()
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/patients/", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["page"] == 1
    patient = body["items"][0]
    assert patient["id"]       == row["id"]
    assert patient["name"]     == "James Wilson"
    assert patient["age"]      == 49
    assert patient["doctor"]   == "Dr. John Smith"
    assert patient["hospital"] == "City General Hospital"
    assert patient["lastReport"] == "CBC"
    assert patient["status"]   == "abnormal"
    assert patient["reports"]  == 1


async def test_patients_pagination_defaults(unit_client):
    row = _fake_patient_row(total_count=1)
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/patients/", headers=AUTH_HEADER)
    body = r.json()
    assert body["page"] == 1
    assert body["page_size"] == 20


async def test_patients_pagination_custom(unit_client):
    row = _fake_patient_row(total_count=1)
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get(
            "/api/v1/patients/?page=2&page_size=5", headers=AUTH_HEADER
        )
    body = r.json()
    assert body["page"] == 2
    assert body["page_size"] == 5


async def test_patients_status_filter_passed(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await unit_client.get(
            "/api/v1/patients/?status=abnormal", headers=AUTH_HEADER
        )
    call_kwargs = mock_fetch.call_args[0][1]
    assert call_kwargs["status"] == "abnormal"


async def test_patients_status_all_normalised_to_none(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await unit_client.get(
            "/api/v1/patients/?status=all", headers=AUTH_HEADER
        )
    call_kwargs = mock_fetch.call_args[0][1]
    assert call_kwargs["status"] is None


async def test_patients_search_passed(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await unit_client.get(
            "/api/v1/patients/?search=James", headers=AUTH_HEADER
        )
    call_kwargs = mock_fetch.call_args[0][1]
    assert call_kwargs["search"] == "James"


# ── integration tests (need real postgres + seed data) ────────────────────────

@pytest.mark.integration
async def test_integration_patients_list(client):
    r = await client.get("/api/v1/patients/", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 2, "Expected seed patients for tenant 1"
    for p in body["items"]:
        assert p["name"]
        assert isinstance(p["age"], int)
        assert p["status"] in ("normal", "abnormal", "review")


@pytest.mark.integration
async def test_integration_patients_search_james(client):
    r = await client.get("/api/v1/patients/?search=James", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert any("James" in p["name"] for p in body["items"])


@pytest.mark.integration
async def test_integration_patients_filter_abnormal(client):
    r = await client.get("/api/v1/patients/?status=abnormal", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    for p in body["items"]:
        assert p["status"] == "abnormal"
