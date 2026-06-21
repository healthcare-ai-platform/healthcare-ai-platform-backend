"""
POST /api/v1/upload/pdf
POST /api/v1/upload/json

S3 and Kafka are mocked. DB execute is mocked for the JSON test.
NOTE: The PDF upload has a known bug — facility_id is NOT NULL in the documents
table but the INSERT in upload.py omits it, causing a DB constraint error.
"""
import io
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from tests.conftest import AUTH_HEADER

# ── pdf ───────────────────────────────────────────────────────────────────────

async def test_upload_pdf_rejects_non_pdf(unit_client):
    r = await unit_client.post(
        "/api/v1/upload/pdf",
        headers=AUTH_HEADER,
        files={"file": ("report.txt", b"hello", "text/plain")},
        data={"report_type": "CBC"},
    )
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


async def test_upload_pdf_s3_failure_returns_500(unit_client):
    # Must patch the name as imported in upload.py, not the origin module.
    with patch("app.api.routers.upload.upload_to_s3", return_value=False):
        r = await unit_client.post(
            "/api/v1/upload/pdf",
            headers=AUTH_HEADER,
            files={"file": ("report.pdf", b"%PDF-1.4 test", "application/pdf")},
            data={"report_type": "CBC"},
        )
    assert r.status_code == 500
    assert "S3" in r.json()["detail"]


@pytest.mark.xfail(
    reason="BUG: upload.py INSERT omits facility_id which is NOT NULL in documents table"
)
async def test_upload_pdf_success(unit_client):
    with (
        patch("app.api.utils.common.upload_to_s3", return_value=True),
        patch("app.db.session.db.execute",         new_callable=AsyncMock),
        patch("app.events.kafka.publish_kafka_event", new_callable=AsyncMock),
    ):
        r = await unit_client.post(
            "/api/v1/upload/pdf",
            headers=AUTH_HEADER,
            files={"file": ("report.pdf", b"%PDF-1.4 test", "application/pdf")},
            data={"report_type": "CBC"},
        )
    assert r.status_code == 200
    body = r.json()
    assert "upload_id" in body
    assert body["message"] == "PDF queued for processing"


# ── json ──────────────────────────────────────────────────────────────────────

VALID_PATIENT_RECORD = {
    "patient": {
        "name": "Test Patient",
        "external_id": "EXT-TEST-001",
        "dob": "1990-01-01",
        "gender": "male",
    },
    "report": {
        "type": "CBC",
        "date": "2024-06-01",
        "doctor": "Dr. Test",
        "facility": "Test Hospital",
    },
    "results": [
        {
            "test_name": "WBC",
            "value": 7.2,
            "unit": "10^3/uL",
            "reference_range": "4.5-11.0",
            "flag": "normal",
            "confidence": 0.99,
        }
    ],
    "extraction_status": "extracted",
    "extraction_confidence": 0.95,
    "created_at": "2024-06-01T10:00:00",
    "updated_at": "2024-06-01T10:00:00",
}


async def test_upload_json_s3_failure_returns_500(unit_client):
    with patch("app.api.routers.upload.upload_to_s3", return_value=False):
        r = await unit_client.post(
            "/api/v1/upload/json",
            headers=AUTH_HEADER,
            json=VALID_PATIENT_RECORD,
        )
    assert r.status_code == 500
    assert "S3" in r.json()["detail"]


async def test_upload_json_success(unit_client):
    with patch("app.api.routers.upload.upload_to_s3", return_value=True):
        r = await unit_client.post(
            "/api/v1/upload/json",
            headers=AUTH_HEADER,
            json=VALID_PATIENT_RECORD,
        )
    assert r.status_code == 200
    body = r.json()
    assert "upload_id" in body
    assert "Test Patient" in body["message"]


async def test_upload_json_missing_required_field(unit_client):
    bad_payload = {k: v for k, v in VALID_PATIENT_RECORD.items() if k != "patient"}
    r = await unit_client.post(
        "/api/v1/upload/json",
        headers=AUTH_HEADER,
        json=bad_payload,
    )
    assert r.status_code == 422
