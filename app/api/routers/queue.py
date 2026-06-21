from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.schemas import Page
from app.db.session import db

router = APIRouter()


class QueueDocument(BaseModel):
    id: str
    name: str
    type: str
    status: str
    tenant: str


@router.get("/", response_model=Page[QueueDocument])
async def list_queue(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> Page[QueueDocument]:
    tenant_id = current_user["tenant_id"]
    if status == "all":
        status = None

    rows = await db.fetch_all(
        """
        SELECT
            d.document_id::text AS id,
            d.report_type       AS name,
            CASE d.source
                WHEN 'pdf_upload'  THEN 'PDF'
                WHEN 'json_upload' THEN 'JSON'
                WHEN 'hl7'         THEN 'HL7'
                WHEN 'fhir'        THEN 'FHIR'
                ELSE UPPER(d.source)
            END                 AS type,
            d.status,
            t.name              AS tenant,
            COUNT(*) OVER ()    AS total_count
        FROM documents d
        JOIN tenants t ON t.tenant_id = d.tenant_id
        WHERE d.tenant_id = :tenant_id
          AND (:status IS NULL OR d.status = :status)
        ORDER BY d.created_at DESC
        LIMIT :limit OFFSET :offset
        """,
        {
            "tenant_id": tenant_id,
            "status": status,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    )

    total = rows[0]["total_count"] if rows else 0
    items = [
        QueueDocument(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            status=row["status"],
            tenant=row["tenant"],
        )
        for row in rows
    ]
    return Page.build(items, total, page, page_size)
