from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.schemas import Page
from app.db.session import db

router = APIRouter()


class AuditLog(BaseModel):
    id: str
    user: str
    action: str
    resource: str
    ip: str
    time: str
    tenant: str


@router.get("/", response_model=Page[AuditLog])
async def list_audit_logs(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> Page[AuditLog]:
    tenant_id = current_user["tenant_id"]

    rows = await db.fetch_all(
        """
        SELECT
            al.log_id::text                                          AS id,
            u.name                                                   AS username,
            al.action,
            al.resource,
            COALESCE(al.ip_address::text, '')                        AS ip,
            TO_CHAR(al.created_at AT TIME ZONE 'UTC', 'HH12:MI AM') AS time,
            t.name                                                   AS tenant,
            COUNT(*) OVER ()                                         AS total_count
        FROM audit_logs al
        JOIN users u   ON u.user_id    = al.user_id
        JOIN tenants t ON t.tenant_id  = al.tenant_id
        WHERE al.tenant_id = :tenant_id
          AND (:search IS NULL OR
               u.name    ILIKE '%' || :search || '%' OR
               al.action ILIKE '%' || :search || '%' OR
               t.name    ILIKE '%' || :search || '%')
        ORDER BY al.created_at DESC
        LIMIT :limit OFFSET :offset
        """,
        {
            "tenant_id": tenant_id,
            "search": search,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    )

    total = rows[0]["total_count"] if rows else 0
    items = [
        AuditLog(
            id=row["id"],
            user=row["username"],
            action=row["action"],
            resource=row["resource"],
            ip=row["ip"],
            time=row["time"],
            tenant=row["tenant"],
        )
        for row in rows
    ]
    return Page.build(items, total, page, page_size)
