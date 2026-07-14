from datetime import datetime
import io
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.utils.common import common_logger, upload_to_s3
from app.db.session import db
from app.events.kafka import publish_kafka_event

router = APIRouter()

UPLOAD_DIR = Path("uploads/pdf")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

S3_BUCKET = os.getenv("S3_BUCKET_NAME", "")

# Roles that cannot upload at all
UPLOAD_BLOCKED_ROLES = {"analyst", "viewer"}

# Per-role allowed report types (None = all types allowed)
ROLE_ALLOWED_TYPES: dict[str, set[str] | None] = {
    "doctor":       {"clinical_note", "prescription", "discharge_summary", "radiology"},
    "ops":          None,
    "manager":      None,
    "tenant_admin": None,
    "platform_admin": None,
}

# Report types that require clinical authorship — never uploadable by non-clinical
# roles, even though those roles otherwise have no fixed allowlist (None above).
CLINICAL_TYPES = {"clinical_note", "prescription", "discharge_summary"}

ROLE_BLOCKED_TYPES: dict[str, set[str]] = {
    "ops": CLINICAL_TYPES,
}


class Patient(BaseModel):
    name: str
    external_id: str
    dob: str
    gender: str


class Report(BaseModel):
    type: str
    date: str
    doctor: str
    facility: str


class TestResult(BaseModel):
    test_name: str
    value: float
    unit: str
    reference_range: str
    flag: Optional[str] = None
    confidence: float


class PatientRecord(BaseModel):
    patient: Patient
    report: Report
    results: list[TestResult]
    extraction_status: str
    extraction_confidence: float
    created_at: str
    updated_at: str


class UploadResponse(BaseModel):
    upload_id: str
    message: str


@router.post("/pdf", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    report_type: str = Form(...),
    current_user: dict = Depends(get_current_user)   # extract from auth token
) -> UploadResponse:

    # 1. Validate
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files accepted.")

    role = current_user.get("role", "")
    if role in UPLOAD_BLOCKED_ROLES:
        raise HTTPException(status_code=403, detail=f"Your role ({role}) is not permitted to upload documents.")

    allowed_types = ROLE_ALLOWED_TYPES.get(role)
    if allowed_types is not None and report_type not in allowed_types:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' may not upload '{report_type}'. Allowed: {', '.join(sorted(allowed_types))}.",
        )

    if report_type in ROLE_BLOCKED_TYPES.get(role, set()):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' may not upload '{report_type}' — requires clinical authorship.",
        )

    # 2. Generate IDs — never trust user input for paths
    document_id = str(uuid.uuid4())
    tenant_id   = current_user["tenant_id"]
    user_id     = current_user["user_id"]
    today       = datetime.utcnow()

    # documents.facility_id is NOT NULL — fall back to the tenant's first facility
    # when the uploader has none assigned (facility_id isn't populated on invite/create yet).
    facility_id = current_user.get("facility_id")
    if not facility_id:
        facility_row = await db.fetch_one(
            "SELECT facility_id::text AS facility_id FROM facilities WHERE tenant_id = :tenant_id ORDER BY created_at LIMIT 1",
            {"tenant_id": tenant_id},
        )
        if not facility_row:
            raise HTTPException(
                status_code=400,
                detail="This tenant has no facilities yet. Create one via "
                       "POST /api/v1/tenants/{tenant_id}/facilities before uploading documents.",
            )
        facility_id = facility_row["facility_id"]

    # 3. Build S3 key — no local disk involved
    s3_key = f"raw/{tenant_id}/{today.year}/{today.month:02d}/{today.day:02d}/{document_id}.pdf"

    # 4. Stream directly to S3

    success = upload_to_s3(file.file, S3_BUCKET, s3_key)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to upload PDF to S3.")
    # 5. Write metadata to Postgres (status = received)
    await db.execute("""
        INSERT INTO documents
          (document_id, tenant_id, facility_id, uploaded_by, report_type, source, s3_path, status, created_at)
        VALUES
          (:document_id, :tenant_id, :facility_id, :user_id, :report_type, 'pdf_upload', :s3_path, 'received', NOW())
    """, {
        "document_id": document_id,
        "tenant_id":   tenant_id,
        "facility_id": facility_id,
        "user_id":     user_id,
        "report_type": report_type,
        "s3_path":     f"s3://{S3_BUCKET}/{s3_key}"
    })

    # 6. Publish Kafka event
    await publish_kafka_event("healthai.report.received", {
        "document_id": document_id,
        "user_id":     user_id,
        "tenant_id":   tenant_id,
        "source":      "pdf_upload",
        "report_type": report_type,
        "s3_path":     f"s3://{S3_BUCKET}/{s3_key}",
        "uploaded_at": today.isoformat()
    })

    # 7. Return 202 — work is queued, not done
    return UploadResponse(
        upload_id=document_id,
        message="PDF queued for processing",
    )


@router.post("/json", response_model=UploadResponse)
async def upload_json(
    payload: PatientRecord,
    current_user: dict = Depends(get_current_user)
    ) -> UploadResponse:
    document_id = str(uuid.uuid4())
    common_logger(f"JSON record received for patient '{payload.patient.name}' (id={document_id})")

    tenant_id   = current_user["tenant_id"]
    user_id     = current_user["user_id"]
    report_type = payload.report.type
    today       = datetime.utcnow()

    # documents.facility_id is NOT NULL — fall back to the tenant's first facility
    # when the uploader has none assigned (facility_id isn't populated on invite/create yet).
    facility_id = current_user.get("facility_id")
    if not facility_id:
        facility_row = await db.fetch_one(
            "SELECT facility_id::text AS facility_id FROM facilities WHERE tenant_id = :tenant_id ORDER BY created_at LIMIT 1",
            {"tenant_id": tenant_id},
        )
        if not facility_row:
            raise HTTPException(
                status_code=400,
                detail="This tenant has no facilities yet. Create one via "
                       "POST /api/v1/tenants/{tenant_id}/facilities before uploading documents.",
            )
        facility_id = facility_row["facility_id"]

    s3_key = f"raw/{tenant_id}/{today.year}/{today.month:02d}/{today.day:02d}/{document_id}.json"

    success = upload_to_s3(io.BytesIO(payload.model_dump_json().encode("utf-8")), S3_BUCKET, s3_key)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to upload JSON to S3.")

    await db.execute("""
        INSERT INTO documents
          (document_id, tenant_id, facility_id, uploaded_by, report_type, source, s3_path, status, created_at)
        VALUES
          (:document_id, :tenant_id, :facility_id, :user_id, :report_type, 'json_upload', :s3_path, 'received', NOW())
    """, {
        "document_id": document_id,
        "tenant_id":   tenant_id,
        "facility_id": facility_id,
        "user_id":     user_id,
        "report_type": report_type,
        "s3_path":     f"s3://{S3_BUCKET}/{s3_key}",
    })

    await publish_kafka_event("healthai.report.received", {
        "document_id": document_id,
        "user_id":     user_id,
        "tenant_id":   tenant_id,
        "source":      "json_upload",
        "report_type": report_type,
        "s3_path":     f"s3://{S3_BUCKET}/{s3_key}",
        "uploaded_at": today.isoformat(),
    })

    return UploadResponse(upload_id=document_id, message=f"Record for patient '{payload.patient.name}' received.")
