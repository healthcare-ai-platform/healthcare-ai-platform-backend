"""
GET /api/v1/queue/
"""
import pytest
from unittest.mock import patch

from tests.conftest import AUTH_HEADER


def _fake_doc_row(**overrides):
    base = {
        "id":          "55555555-0000-0000-0000-000000000001",
        "name":        "CBC",
        "type":        "PDF",
        "status":      "received",
        "tenant":      "City General Health System",
        "total_count": 1,
    }
    base.update(overrides)
    return base


# ── unit tests ────────────────────────────────────────────────────────────────

async def test_queue_empty(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]):
        r = await unit_client.get("/api/v1/queue/", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_queue_item_shape(unit_client):
    row = _fake_doc_row()
    with patch("app.db.session.db.fetch_all", return_value=[row]):
        r = await unit_client.get("/api/v1/queue/", headers=AUTH_HEADER)
    body = r.json()
    assert body["total"] == 1
    doc = body["items"][0]
    assert doc["id"]     == row["id"]
    assert doc["name"]   == "CBC"
    assert doc["type"]   == "PDF"
    assert doc["status"] == "received"
    assert doc["tenant"] == "City General Health System"


async def test_queue_status_filter_passed(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await unit_client.get("/api/v1/queue/?status=received", headers=AUTH_HEADER)
    params = mock_fetch.call_args[0][1]
    assert params["status"] == "received"


async def test_queue_status_all_normalised(unit_client):
    with patch("app.db.session.db.fetch_all", return_value=[]) as mock_fetch:
        await unit_client.get("/api/v1/queue/?status=all", headers=AUTH_HEADER)
    params = mock_fetch.call_args[0][1]
    assert params["status"] is None


async def test_queue_valid_statuses(unit_client):
    valid = ["received", "ocr", "extracting", "extracted", "validated", "loaded", "failed"]
    for status in valid:
        row = _fake_doc_row(status=status)
        with patch("app.db.session.db.fetch_all", return_value=[row]):
            r = await unit_client.get(f"/api/v1/queue/?status={status}", headers=AUTH_HEADER)
        assert r.status_code == 200, f"Unexpected error for status={status}"


# ── integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_integration_queue_list(client):
    r = await client.get("/api/v1/queue/", headers=AUTH_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3, "Expected 3 seed documents for tenant 1"
    for doc in body["items"]:
        assert doc["status"] in (
            "received", "ocr", "extracting", "extracted", "validated", "loaded", "failed"
        )
        assert doc["type"] in ("PDF", "JSON", "HL7", "FHIR")


@pytest.mark.integration
async def test_integration_queue_filter_loaded(client):
    r = await client.get("/api/v1/queue/?status=loaded", headers=AUTH_HEADER)
    assert r.status_code == 200
    for doc in r.json()["items"]:
        assert doc["status"] == "loaded"
